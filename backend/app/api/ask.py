import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Memory, User
from app.core.config import settings
from app.schemas.rag import AskPassage, AskRequest, AskResponse, AskSource, SearchPlan, StructuredItem
from app.services.ai_provider import (
    AIProviderNotConfigured,
    AIProviderUnavailable,
    answer_with_context,
    preferred_generation_provider,
)
from app.services.metadata_normalizer import normalize_memory
from app.services.query_planner import normalize_datetime, plan_search
from app.services.retrieval import hybrid_search, lexical_terms, make_excerpt
from app.services.structured_search import execute_structured_search, interpreted_filters, matches_plan
from app.services.auth import get_current_user
from app.services.output_safety import redact_public_text


router = APIRouter(prefix="/ask", tags=["RAG"])
logger = logging.getLogger(__name__)
_INSUFFICIENT = "I do not have enough information in Chrono to answer that question."
_CITATION_RE = re.compile(r"\[(\d+)\]")


def _extractive_evidence_covers_question(question: str, results: list[dict]) -> bool:
    terms = [term for term in lexical_terms(question) if len(term) > 1]
    if not terms:
        return False
    evidence_words = set(re.findall(
        r"[a-z0-9]+",
        " ".join(f"{result['title']} {result['content']}" for result in results).lower(),
    ))
    matched = 0
    for term in terms:
        variants = {term, f"{term}s", f"{term}es"}
        if term.endswith("s"):
            variants.add(term[:-1])
        matched += bool(variants.intersection(evidence_words))
    return matched / len(terms) >= settings.RAG_MIN_FILE_TERM_COVERAGE


def _merge_explicit_filters(plan: SearchPlan, data: AskRequest) -> SearchPlan:
    updates = {"limit": data.limit}
    for field_name in ("source", "event_type", "mime_type", "start", "end"):
        value = getattr(data, field_name)
        if value is not None:
            updates[field_name] = normalize_datetime(value) if field_name in {"start", "end"} else value
    if (data.start or data.end) and not plan.date_field:
        updates["date_field"] = "event_date"
    return SearchPlan.model_validate({**plan.model_dump(), **updates})


def _retrieval_results(
    db: Session, data: AskRequest, plan: SearchPlan, user_id: str, timings: dict[str, float]
):
    use_event_dates = plan.date_field in {None, "event_date"}
    results, mode = hybrid_search(
        db,
        user_id=user_id,
        query_text=plan.query_text or data.question,
        limit=min(plan.limit * 4, 50),
        source=plan.source,
        event_type=plan.event_type,
        mime_type=plan.mime_type,
        mime_types=plan.mime_types,
        start=plan.start if use_event_dates else None,
        end=plan.end if use_event_dates else None,
        timings=timings,
        diagnostics=timings,
    )
    memory_ids = [result["memory_id"] for result in results]
    memories = {
        str(memory.id): normalize_memory(memory)
        for memory in db.query(Memory).filter(
            Memory.user_id == user_id, Memory.id.in_(memory_ids)
        ).all()
    } if memory_ids else {}
    filtered = [
        result for result in results
        if (metadata := memories.get(result["memory_id"])) is not None
        and matches_plan(metadata, plan)
    ]
    return filtered[:plan.limit], mode


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


def _finalize_citations(
    db: Session,
    *,
    answer: str,
    results: list[dict],
    question: str,
    user_id: str,
) -> tuple[str, list[AskSource]]:
    """Expose cited evidence only and keep public citation numbers contiguous."""
    referenced = [int(value) for value in _CITATION_RE.findall(answer)]
    valid_old_numbers = list(dict.fromkeys(
        number for number in referenced if 1 <= number <= len(results)
    ))
    if referenced:
        if not valid_old_numbers:
            return _INSUFFICIENT, []
        citation_map = {
            old_number: new_number
            for new_number, old_number in enumerate(valid_old_numbers, start=1)
        }

        def replace_marker(match: re.Match[str]) -> str:
            old_number = int(match.group(1))
            new_number = citation_map.get(old_number)
            return f"[{new_number}]" if new_number is not None else ""

        finalized_answer = _CITATION_RE.sub(replace_marker, answer)
        selected = [results[number - 1] for number in valid_old_numbers]
    else:
        # A provider may omit markers despite grounded context. In that case,
        # expose only the highest-ranked file (up to the configured chunk cap),
        # never every internal retrieval candidate.
        top_memory_id = results[0]["memory_id"] if results else None
        selected = [
            result for result in results if result["memory_id"] == top_memory_id
        ][:max(1, settings.RAG_MAX_CHUNKS_PER_FILE)]
        finalized_answer = answer
    return finalized_answer, _sources(db, selected, question, user_id)


def _content_question(
    db: Session, data: AskRequest, plan: SearchPlan, user_id: str, timings: dict[str, float]
) -> AskResponse:
    results, mode = _retrieval_results(db, data, plan, user_id, timings)
    filters = interpreted_filters(plan)
    if not results:
        return AskResponse(
            answer=_INSUFFICIENT, retrieval_mode=mode, sources=[],
            intent="content_question", interpreted_filters=filters,
        )
    context_started = perf_counter()
    context_sources = _sources(db, results, data.question, user_id)
    context_parts = [
        f"[{citation}] Title: {result['title']}\n"
        f"Date: {result['event_date'].isoformat()}\nContent: {result['content']}"
        for citation, result in enumerate(results, start=1)
    ]
    timings["context_preparation_ms"] = round((perf_counter() - context_started) * 1000, 2)
    try:
        generation_started = perf_counter()
        configured_generation = preferred_generation_provider()
        answer = answer_with_context(data.question, "\n\n".join(context_parts))
        generation_ms = round((perf_counter() - generation_started) * 1000, 2)
        timings["answer_generation_ms"] = generation_ms
        if configured_generation and configured_generation["provider"] == "gemini":
            timings["gemini_generation_ms"] = generation_ms
    except (AIProviderNotConfigured, AIProviderUnavailable):
        generation_ms = round((perf_counter() - generation_started) * 1000, 2)
        timings["answer_generation_ms"] = generation_ms
        if configured_generation and configured_generation["provider"] == "gemini":
            timings["gemini_generation_ms"] = generation_ms
        fallback_started = perf_counter()
        if not _extractive_evidence_covers_question(data.question, results):
            timings["fallback_generation_ms"] = round((perf_counter() - fallback_started) * 1000, 2)
            return AskResponse(
                answer=_INSUFFICIENT, retrieval_mode="lexical-extractive", sources=[],
                intent="content_question", interpreted_filters=filters,
            )
        mode = "lexical-extractive"
        answer = (
            "The most relevant Chrono memory passages are: "
            + " ".join(
                f"[{passage.citation}] {passage.excerpt}"
                for source in context_sources
                for passage in source.passages
            )
        )
        timings["fallback_generation_ms"] = round((perf_counter() - fallback_started) * 1000, 2)
    answer, public_sources = _finalize_citations(
        db,
        answer=answer,
        results=results,
        question=data.question,
        user_id=user_id,
    )
    return AskResponse(
        answer=redact_public_text(answer), retrieval_mode=mode, sources=public_sources,
        intent="content_question", interpreted_filters=filters,
    )


def _content_search(
    db: Session, data: AskRequest, plan: SearchPlan, user_id: str, timings: dict[str, float]
) -> AskResponse:
    results, mode = _retrieval_results(db, data, plan, user_id, timings)
    memory_ids: list[str] = []
    excerpts: dict[str, str] = {}
    for result in results:
        if result["memory_id"] not in memory_ids:
            memory_ids.append(result["memory_id"])
            excerpts[result["memory_id"]] = make_excerpt(result["content"], data.question)
    all_memories = db.query(Memory).filter(Memory.user_id == user_id).all()
    topic_terms = lexical_terms(plan.query_text or data.question)
    title_matches = [
        memory for memory in all_memories
        if str(memory.id) not in memory_ids
        and matches_plan(normalize_memory(memory), plan)
        and topic_terms
        and all(term in memory.title.casefold() for term in topic_terms)
    ]
    memory_ids = ([str(memory.id) for memory in title_matches] + memory_ids)[:plan.limit]
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
            excerpt=redact_public_text(excerpts[memory_id]) if memory_id in excerpts else None,
            open_url=metadata.open_url,
        ))
    return AskResponse(
        answer=(
            f"Chrono found {len(items)} relevant document{'s' if len(items) != 1 else ''}."
            if items else "Chrono found no matching files."
        ),
        retrieval_mode=mode,
        sources=[],
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
    request_started = perf_counter()
    trace_id = uuid4().hex[:12]
    timings: dict[str, float] = {}
    user_id = str(current_user.id)
    planning_started = perf_counter()
    plan = _merge_explicit_filters(plan_search(data.question, limit=data.limit), data)
    timings["query_planning_ms"] = round((perf_counter() - planning_started) * 1000, 2)
    if plan.intent == "content_question":
        response = _content_question(db, data, plan, user_id, timings)
    elif plan.intent == "content_search":
        response = _content_search(db, data, plan, user_id, timings)
    else:
        execution = execute_structured_search(db, user_id=user_id, plan=plan)
        response = AskResponse(
            answer=execution.answer,
            retrieval_mode=execution.retrieval_mode,
            sources=[],
            intent=execution.intent,
            interpreted_filters=execution.interpreted_filters,
            items=execution.items,
        )
    timings["total_request_ms"] = round((perf_counter() - request_started) * 1000, 2)
    logger.info(
        "chrono_ask trace_id=%s intent=%s mode=%s timings_ms=%s",
        trace_id, response.intent, response.retrieval_mode,
        ",".join(f"{key}:{value:.2f}" for key, value in sorted(timings.items())),
    )
    return response
