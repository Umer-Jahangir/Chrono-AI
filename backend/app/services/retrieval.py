from datetime import datetime
import re
from time import perf_counter
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import Memory, MemoryChunk
from app.core.config import settings
from app.services.ai_provider import (
    AIProviderNotConfigured,
    AIProviderUnavailable,
    create_embedding_batch,
)


_QUERY_STOPWORDS = {
    "a", "an", "and", "among", "are", "about", "can", "could", "did", "do",
    "does", "explain", "find", "for", "give", "how", "in", "is", "me", "of",
    "on", "or", "please", "show", "should", "tell", "the", "to", "was", "were",
    "what", "when", "where", "which", "who", "why", "would", "have", "related",
    "file", "files", "document", "documents", "only",
}


def lexical_terms(query_text: str) -> list[str]:
    """Reduce a natural-language question to meaningful full-text terms."""
    return [
        term for term in re.findall(r"\w+", query_text.lower())
        if term not in _QUERY_STOPWORDS
    ][:20]


def make_excerpt(text: str, query_text: str, max_chars: int = 280) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    lowered = cleaned.lower()
    positions = [lowered.find(term) for term in lexical_terms(query_text)]
    positions = [position for position in positions if position >= 0]
    anchor = min(positions) if positions else 0
    start = max(0, anchor - 60)
    end = min(len(cleaned), start + max_chars)
    excerpt = cleaned[start:end].strip()
    if start:
        excerpt = "…" + excerpt
    if end < len(cleaned):
        excerpt += "…"
    return excerpt


def _base_query(
    db: Session,
    user_id: str,
    source: str | None,
    event_type: str | None,
    mime_type: str | None,
    mime_types: list[str] | None,
    start: datetime | None,
    end: datetime | None,
):
    query = db.query(MemoryChunk, Memory).join(Memory, Memory.id == MemoryChunk.memory_id).filter(Memory.user_id == user_id)
    if source:
        query = query.filter(Memory.source == source)
    if event_type:
        query = query.filter(Memory.event_type == event_type)
    normalized_mime = func.btrim(func.split_part(
        func.lower(Memory.metadata_json["mime_type"].as_string()), ";", 1
    ))
    if mime_type:
        query = query.filter(normalized_mime == mime_type.casefold())
    if mime_types:
        query = query.filter(normalized_mime.in_([value.casefold() for value in mime_types]))
    if start:
        query = query.filter(Memory.event_date >= start)
    if end:
        query = query.filter(Memory.event_date <= end)
    return query


def hybrid_search(
    db: Session,
    *,
    user_id: str,
    query_text: str,
    limit: int = 10,
    source: str | None = None,
    event_type: str | None = None,
    mime_type: str | None = None,
    mime_types: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    timings: dict[str, float] | None = None,
    diagnostics: dict[str, float | int] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    candidates = max(limit * 4, 20)
    records: dict[str, tuple[MemoryChunk, Memory]] = {}
    lexical_scores: dict[str, float] = {}
    semantic_scores: dict[str, float] = {}

    terms = lexical_terms(query_text)
    if not terms:
        return [], "lexical"
    lexical_started = perf_counter()
    document = func.to_tsvector("english", func.concat_ws(" ", Memory.title, MemoryChunk.content))
    search_query = func.to_tsquery("english", " | ".join(terms))
    lexical_rank = func.ts_rank_cd(document, search_query)
    lexical = (
        _base_query(db, user_id, source, event_type, mime_type, mime_types, start, end)
        .filter(document.op("@@")(search_query))
        .filter(lexical_rank >= settings.LEXICAL_MIN_RANK)
        .add_columns(lexical_rank.label("lexical_rank"))
        .order_by(lexical_rank.desc(), Memory.event_date.desc())
        .limit(candidates)
        .all()
    )
    if timings is not None:
        timings["lexical_retrieval_ms"] = round((perf_counter() - lexical_started) * 1000, 2)
    for chunk, memory, raw_rank in lexical:
        key = str(chunk.id)
        records[key] = (chunk, memory)
        lexical_scores[key] = float(raw_rank or 0.0)

    mode = "lexical"
    try:
        embedding_started = perf_counter()
        batch = create_embedding_batch([query_text], task_type="RETRIEVAL_QUERY")
        if timings is not None:
            timings["embedding_generation_ms"] = round((perf_counter() - embedding_started) * 1000, 2)
        query_vector = batch.vectors[0]
        distance = MemoryChunk.embedding.cosine_distance(query_vector)
        vector_started = perf_counter()
        semantic = (
            _base_query(db, user_id, source, event_type, mime_type, mime_types, start, end)
            .filter(MemoryChunk.embedding.is_not(None))
            .filter(MemoryChunk.embedding_provider == batch.spec.provider)
            .filter(MemoryChunk.embedding_model == batch.spec.model)
            .filter(MemoryChunk.embedding_dimensions == batch.spec.dimensions)
            .filter(distance <= 1.0 - settings.RAG_MIN_SEMANTIC_CANDIDATE)
            .add_columns(distance.label("distance"))
            .order_by(distance.asc())
            .limit(candidates)
            .all()
        )
        if timings is not None:
            timings["vector_retrieval_ms"] = round((perf_counter() - vector_started) * 1000, 2)
        for chunk, memory, raw_distance in semantic:
            key = str(chunk.id)
            records[key] = (chunk, memory)
            semantic_scores[key] = max(0.0, min(1.0, 1.0 - float(raw_distance)))
        if semantic:
            mode = "hybrid"
    except (AIProviderNotConfigured, AIProviderUnavailable):
        if timings is not None:
            timings.setdefault("embedding_generation_ms", round((perf_counter() - embedding_started) * 1000, 2))

    if diagnostics is not None:
        diagnostics["candidate_count"] = len(records)

    words_per_memory: dict[str, set[str]] = {}
    for chunk, memory in records.values():
        memory_key = str(memory.id)
        words_per_memory.setdefault(memory_key, set()).update(
            re.findall(r"[a-z0-9]+", f"{memory.title} {chunk.content}".casefold())
        )
    passage_scores: dict[str, float] = {}
    lexical_signals: dict[str, float] = {}
    coverage_by_memory: dict[str, float] = {}
    for memory_key, words in words_per_memory.items():
        coverage_by_memory[memory_key] = sum(term in words for term in terms) / len(terms)

    # Exact lexical evidence is primary. Semantic similarity can rescue a true
    # paraphrase, but a merely-near vector must cross a substantially higher
    # semantic-only floor. Scores are absolute and normalized to [0, 1].
    for key, (chunk, _memory) in records.items():
        words = set(re.findall(r"[a-z0-9]+", f"{_memory.title} {chunk.content}".casefold()))
        local_coverage = sum(term in words for term in terms) / len(terms)
        rank_signal = min(
            lexical_scores.get(key, 0.0) / max(settings.RAG_LEXICAL_RANK_SATURATION, 0.001),
            1.0,
        )
        lexical_signal = 0.70 * local_coverage + 0.30 * rank_signal
        semantic_signal = semantic_scores.get(key, 0.0)
        lexical_signals[key] = lexical_signal
        passage_scores[key] = (
            0.70 * lexical_signal + 0.30 * semantic_signal
            if lexical_scores.get(key, 0.0) > 0
            else 0.60 * semantic_signal
        )

    keys_by_memory: dict[str, list[str]] = {}
    for key, (_chunk, memory) in records.items():
        keys_by_memory.setdefault(str(memory.id), []).append(key)

    accepted_files: list[tuple[str, float, list[str]]] = []
    for memory_key, keys in keys_by_memory.items():
        ordered_keys = sorted(keys, key=lambda key: passage_scores[key], reverse=True)
        maximum_semantic = max((semantic_scores.get(key, 0.0) for key in keys), default=0.0)
        has_lexical = any(lexical_scores.get(key, 0.0) > 0 for key in keys)
        file_coverage = coverage_by_memory[memory_key]
        evidence_gate = (
            has_lexical and (
                len(terms) < 3 or file_coverage >= settings.RAG_MIN_FILE_TERM_COVERAGE
            )
        ) or maximum_semantic >= settings.RAG_MIN_SEMANTIC_ONLY
        best_score = passage_scores[ordered_keys[0]]
        if not evidence_gate or best_score < settings.RAG_MIN_FINAL_RELEVANCE:
            continue
        supporting = [
            key for key in ordered_keys
            if passage_scores[key] >= settings.RAG_MIN_FINAL_RELEVANCE
            or lexical_scores.get(key, 0.0) > 0
        ][:max(1, settings.RAG_MAX_CHUNKS_PER_FILE)]
        file_score = min(1.0, best_score + 0.05 * min(max(len(supporting) - 1, 0), 1))
        accepted_files.append((memory_key, file_score, supporting))

    accepted_files.sort(key=lambda item: item[1], reverse=True)
    results = []
    for _memory_key, file_score, keys in accepted_files:
        for key in keys:
            chunk, memory = records[key]
            results.append({
                "chunk_id": key,
                "memory_id": str(memory.id),
                "score": round(file_score, 6),
                "lexical_score": round(lexical_signals[key], 6),
                "semantic_score": round(semantic_scores.get(key, 0.0), 6),
                "final_score": round(passage_scores[key], 6),
                "title": memory.title,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "source": memory.source,
                "source_id": memory.source_id,
                "event_type": memory.event_type,
                "event_date": memory.event_date,
                "file_url": memory.file_url,
                "metadata": chunk.metadata_json,
            })
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    if diagnostics is not None:
        diagnostics["accepted_passage_count"] = len(results)
        diagnostics["rejected_passage_count"] = max(0, len(records) - len(results))
        diagnostics["accepted_file_count"] = len({result["memory_id"] for result in results})
        for label, values in (
            ("lexical", list(lexical_signals.values())),
            ("semantic", list(semantic_scores.values())),
            ("final", list(passage_scores.values())),
        ):
            diagnostics[f"{label}_score_min"] = round(min(values), 3) if values else 0.0
            diagnostics[f"{label}_score_max"] = round(max(values), 3) if values else 0.0
    return results, mode
