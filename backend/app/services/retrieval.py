from datetime import datetime
import re
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
    "what", "when", "where", "which", "who", "why", "would",
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
    start: datetime | None,
    end: datetime | None,
):
    query = db.query(MemoryChunk, Memory).join(Memory, Memory.id == MemoryChunk.memory_id).filter(Memory.user_id == user_id)
    if source:
        query = query.filter(Memory.source == source)
    if event_type:
        query = query.filter(Memory.event_type == event_type)
    if mime_type:
        query = query.filter(Memory.metadata_json["mime_type"].as_string() == mime_type)
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
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[list[dict[str, Any]], str]:
    candidates = max(limit * 4, 20)
    scores: dict[str, float] = {}
    records: dict[str, tuple[MemoryChunk, Memory]] = {}

    terms = lexical_terms(query_text)
    if not terms:
        return [], "lexical"
    document = func.to_tsvector("english", func.concat_ws(" ", Memory.title, MemoryChunk.content))
    search_query = func.plainto_tsquery("english", " ".join(terms))
    lexical_rank = func.ts_rank_cd(document, search_query)
    lexical = (
        _base_query(db, user_id, source, event_type, mime_type, start, end)
        .filter(document.op("@@")(search_query))
        .filter(lexical_rank >= settings.LEXICAL_MIN_RANK)
        .add_columns(lexical_rank.label("lexical_rank"))
        .order_by(lexical_rank.desc(), Memory.event_date.desc())
        .limit(candidates)
        .all()
    )
    for rank, (chunk, memory, _) in enumerate(lexical, start=1):
        key = str(chunk.id)
        records[key] = (chunk, memory)
        scores[key] = scores.get(key, 0.0) + 0.35 / (60 + rank)

    mode = "lexical"
    try:
        batch = create_embedding_batch([query_text], task_type="RETRIEVAL_QUERY")
        query_vector = batch.vectors[0]
        distance = MemoryChunk.embedding.cosine_distance(query_vector)
        semantic = (
            _base_query(db, user_id, source, event_type, mime_type, start, end)
            .filter(MemoryChunk.embedding.is_not(None))
            .filter(MemoryChunk.embedding_provider == batch.spec.provider)
            .filter(MemoryChunk.embedding_model == batch.spec.model)
            .filter(MemoryChunk.embedding_dimensions == batch.spec.dimensions)
            .filter(distance <= 1.0 - settings.SEMANTIC_MIN_SIMILARITY)
            .add_columns(distance.label("distance"))
            .order_by(distance.asc())
            .limit(candidates)
            .all()
        )
        for rank, (chunk, memory, _) in enumerate(semantic, start=1):
            key = str(chunk.id)
            records[key] = (chunk, memory)
            scores[key] = scores.get(key, 0.0) + 0.65 / (60 + rank)
        if semantic:
            mode = "hybrid"
    except (AIProviderNotConfigured, AIProviderUnavailable):
        pass

    ordered = sorted(scores, key=scores.get, reverse=True)
    results = []
    chunks_per_memory: dict[str, int] = {}
    for key in ordered:
        chunk, memory = records[key]
        memory_key = str(memory.id)
        if chunks_per_memory.get(memory_key, 0) >= 2:
            continue
        results.append({
            "chunk_id": key,
            "memory_id": str(memory.id),
            "score": round(scores[key], 8),
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
        chunks_per_memory[memory_key] = chunks_per_memory.get(memory_key, 0) + 1
        if len(results) >= limit:
            break
    return results, mode
