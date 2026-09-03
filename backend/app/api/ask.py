import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Memory, User
from app.schemas.rag import AskPassage, AskRequest, AskResponse, AskSource, SearchPlan, StructuredItem
from app.services.ai_provider import AIProviderNotConfigured, AIProviderUnavailable, answer_with_context
from app.services.metadata_normalizer import normalize_memory
from app.services.query_planner import normalize_datetime, plan_search
from app.services.retrieval import hybrid_search, lexical_terms, make_excerpt
from app.services.structured_search import execute_structured_search, interpreted_filters
from app.services.auth import get_current_user
from app.services.output_safety import redact_public_text


router = APIRouter(prefix="/ask", tags=["RAG"])
_INSUFFICIENT = "I do not have enough information in Chrono to answer that question."


def _extractive_evidence_covers_question(question: str, results: list[dict]) -> bool:
    terms = [term for term in lexical_terms(question) if len(term) > 1]
    if not terms:
        return False
    evidence_words = set(re.findall(r"\w+", " ".join(result["content"] for result in results).lower()))
    for term in terms:
        variants = {term, f"{term}s", f"{term}es"}
        if term.endswith("s"):
            variants.add(term[:-1])
        if not variants.intersection(evidence_words):
            return False
    return True


def _merge_explicit_filters(plan: SearchPlan, data: AskRequest) -> SearchPlan:
    updates = {"limit": data.limit}
    for field_name in ("source", "event_type", "mime_type", "start", "end"):
        value = getattr(data, field_name)
        if value is not None:
            updates[field_name] = normalize_datetime(value) if field_name in {"start", "end"} else value
    if (data.start or data.end) and not plan.date_field:
        updates["date_field"] = "event_date"
    return plan.model_copy(update=updates)


def _retrieval_results(db: Session, data: AskRequest, plan: SearchPlan, user_id: str):
    return hybrid_search(
        db,
        user_id=user_id,
        query_text=plan.query_text or data.question,
        limit=plan.limit,
        source=plan.source,
        event_type=plan.event_type,
        mime_type=plan.mime_type,
        start=plan.start,
        end=plan.end,
    )


def _sources(db: Session, results: list[dict], question: str, user_id: str) -> list[AskSource]:
    memory_ids = list(dict.fromkeys(result["memory_id"] for result in results))
    memories = {
        str(memory.id): normalize_memory(memory)
        for memory in db.query(Memory).filter(
            Memory.user_id == user_id, Memory.id.in_(memory_ids)
        ).all()
    } if memory_ids else {}
    grouped: dict[str, dict] = {}
    for citation, result in enumerate(results, start=1):
        memory_id = result["memory_id"]
        metadata = memories.get(memory_id)
        if metadata is None:
            continue
        passage = AskPassage(
            citation=citation,
            excerpt=redact_public_text(make_excerpt(result["content"], question, max_chars=240)),
        )
        group = grouped.setdefault(memory_id, {"metadata": metadata, "passages": []})
        group["passages"].append(passage)
    return [
        AskSource(
            citation=group["passages"][0].citation,
            title=group["metadata"].title,
            excerpt=group["passages"][0].excerpt,
            event_date=group["metadata"].event_date,
            open_url=group["metadata"].open_url,
            passages=group["passages"],
        )
        for group in grouped.values()
    ]


def _content_question(db: Session, data: AskRequest, plan: SearchPlan, user_id: str) -> AskResponse:
    results, mode = _retrieval_results(db, data, plan, user_id)
    filters = interpreted_filters(plan)
    if not results:
        return AskResponse(
            answer=_INSUFFICIENT, retrieval_mode=mode, sources=[],
            intent="content_question", interpreted_filters=filters,
        )
    sources = _sources(db, results, data.question, user_id)
    context_parts = [
        f"[{citation}] Title: {result['title']}\n"
        f"Date: {result['event_date'].isoformat()}\nContent: {result['content']}"
        for citation, result in enumerate(results, start=1)
    ]
    try:
        answer = answer_with_context(data.question, "\n\n".join(context_parts))
    except (AIProviderNotConfigured, AIProviderUnavailable):
        if not _extractive_evidence_covers_question(data.question, results):
            return AskResponse(
                answer=_INSUFFICIENT, retrieval_mode="lexical-extractive", sources=[],
                intent="content_question", interpreted_filters=filters,
            )
        mode = "lexical-extractive"
        answer = (
            "AI generation is not configured. The most relevant Chrono memory passages are: "
            + " ".join(
                f"[{passage.citation}] {passage.excerpt}"
                for source in sources
                for passage in source.passages
            )
        )
    return AskResponse(
        answer=redact_public_text(answer), retrieval_mode=mode, sources=sources,
        intent="content_question", interpreted_filters=filters,
    )


def _content_search(db: Session, data: AskRequest, plan: SearchPlan, user_id: str) -> AskResponse:
    results, mode = _retrieval_results(db, data, plan, user_id)
    sources = _sources(db, results, data.question, user_id)
    memory_ids: list[str] = []
    excerpts: dict[str, str] = {}
    for result in results:
        if result["memory_id"] not in memory_ids:
            memory_ids.append(result["memory_id"])
            excerpts[result["memory_id"]] = make_excerpt(result["content"], data.question)
    memories = {
        str(memory.id): memory
        for memory in db.query(Memory).filter(
            Memory.id.in_(memory_ids), Memory.user_id == user_id
        ).all()
    } if memory_ids else {}
    items = []
    for memory_id in memory_ids:
        memory = memories.get(memory_id)
        if memory is None:
            continue
        metadata = normalize_memory(memory)
        items.append(StructuredItem(
            title=metadata.title,
            source=metadata.source,
            mime_type=metadata.mime_type,
            item_type="folder" if metadata.is_folder else "file",
            event_type=metadata.event_type,
            event_date=metadata.event_date,
            created_time=metadata.created_time,
            modified_time=metadata.modified_time,
            owner_display_names=[person.display_name for person in metadata.owners if person.display_name],
            excerpt=redact_public_text(excerpts[memory_id]),
            open_url=metadata.open_url,
        ))
    return AskResponse(
        answer=f"Chrono found {len(items)} relevant document{'s' if len(items) != 1 else ''}.",
        retrieval_mode=mode,
        sources=sources,
        intent="content_search",
        interpreted_filters=interpreted_filters(plan),
        items=items,
    )


@router.post("", response_model=AskResponse)
def ask_chrono(
    data: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    user_id = str(current_user.id)
    plan = _merge_explicit_filters(plan_search(data.question, limit=data.limit), data)
    if plan.intent == "content_question":
        return _content_question(db, data, plan, user_id)
    if plan.intent == "content_search":
        return _content_search(db, data, plan, user_id)
    execution = execute_structured_search(db, user_id=user_id, plan=plan)
    return AskResponse(
        answer=execution.answer,
        retrieval_mode=execution.retrieval_mode,
        sources=[],
        intent=execution.intent,
        interpreted_filters=execution.interpreted_filters,
        items=execution.items,
    )
