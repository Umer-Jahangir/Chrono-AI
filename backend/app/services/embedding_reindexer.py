from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Memory, MemoryChunk
from app.services.ai_provider import (
    EmbeddingSpec,
    create_embedding_batch_for_spec,
    preferred_embedding_spec,
    provider_error_category,
)
from app.services.chunking import estimate_tokens, split_for_embedding


ProgressReporter = Callable[[dict], None]
_PERMANENT_SKIP_CATEGORIES = {"bad_request", "empty_text", "input_too_large"}


@dataclass
class WorkItem:
    chunk: MemoryChunk
    memory: Memory
    text: str
    estimated_tokens: int


def _matches(chunk: MemoryChunk, spec: EmbeddingSpec) -> bool:
    return bool(
        chunk.embedding is not None
        and chunk.embedding_provider == spec.provider
        and chunk.embedding_model == spec.model
        and chunk.embedding_dimensions == spec.dimensions
    )


def _permanently_rejected(chunk: MemoryChunk, spec: EmbeddingSpec) -> bool:
    return bool(
        chunk.embedding_error_category in _PERMANENT_SKIP_CATEGORIES
        and chunk.embedding_error_provider == spec.provider
        and chunk.embedding_error_model == spec.model
    )


def _clear_error(chunk: MemoryChunk) -> None:
    chunk.embedding_error_category = None
    chunk.embedding_error_provider = None
    chunk.embedding_error_model = None
    chunk.embedding_error_at = None


def _mark_error(chunk: MemoryChunk, spec: EmbeddingSpec, category: str) -> None:
    chunk.embedding_error_category = category
    chunk.embedding_error_provider = spec.provider
    chunk.embedding_error_model = spec.model
    chunk.embedding_error_at = datetime.now(timezone.utc)


def _safe_error(item: WorkItem, category: str, batch_size: int) -> dict:
    return {
        "error_category": category,
        "memory_title": item.memory.title,
        "chunk_index": item.chunk.chunk_index,
        "character_count": len(item.text),
        "estimated_token_count": item.estimated_tokens,
        "batch_size": batch_size,
    }


def _bounded_batches(items: list[WorkItem]) -> list[list[WorkItem]]:
    batches: list[list[WorkItem]] = []
    current: list[WorkItem] = []
    tokens = 0
    for item in items:
        would_overflow = bool(current) and (
            len(current) >= settings.GEMINI_EMBEDDING_BATCH_SIZE
            or tokens + item.estimated_tokens > settings.GEMINI_EMBEDDING_BATCH_TOKEN_LIMIT
        )
        if would_overflow:
            batches.append(current)
            current = []
            tokens = 0
        current.append(item)
        tokens += item.estimated_tokens
    if current:
        batches.append(current)
    return batches


def _apply_success(db: Session, items: list[WorkItem], vectors: list[list[float]], spec: EmbeddingSpec) -> None:
    for item, vector in zip(items, vectors, strict=True):
        item.chunk.embedding = vector
        item.chunk.embedding_provider = spec.provider
        item.chunk.embedding_model = spec.model
        item.chunk.embedding_dimensions = spec.dimensions
        _clear_error(item.chunk)
    db.commit()


def _embed_one_after_bad_batch(
    db: Session,
    item: WorkItem,
    spec: EmbeddingSpec,
    report: ProgressReporter,
) -> tuple[int, int]:
    try:
        result = create_embedding_batch_for_spec(
            [item.text], task_type="RETRIEVAL_DOCUMENT", spec=spec
        )
        _apply_success(db, [item], result.vectors, result.spec)
        return 1, 0
    except Exception as exc:
        category, permanent = provider_error_category(exc)
        if permanent:
            _mark_error(item.chunk, spec, category)
            db.commit()
        report(_safe_error(item, category, 1))
        return 0, 1


def reindex_embeddings(
    db: Session,
    *,
    user_id: str,
    source: str = "google_drive",
    missing_only: bool = True,
    report: ProgressReporter | None = None,
) -> dict:
    report = report or (lambda _event: None)
    spec = preferred_embedding_spec()
    if spec is None:
        raise RuntimeError("No embedding provider is configured")
    if spec.dimensions != 1536:
        raise RuntimeError("Active embedding dimensions must be exactly 1536")

    rows = (
        db.query(MemoryChunk, Memory)
        .join(Memory, Memory.id == MemoryChunk.memory_id)
        .filter(Memory.user_id == user_id, Memory.source == source)
        .order_by(Memory.created_at.asc(), MemoryChunk.chunk_index.asc())
        .all()
    )
    total = len(rows)
    already_embedded = sum(_matches(chunk, spec) for chunk, _memory in rows)
    skipped = 0
    work: list[WorkItem] = []
    next_indices: dict[str, int] = {}
    for chunk, memory in rows:
        if missing_only and _matches(chunk, spec):
            continue
        if missing_only and _permanently_rejected(chunk, spec):
            skipped += 1
            continue

        pieces = split_for_embedding(
            chunk.content, token_limit=settings.GEMINI_EMBEDDING_INPUT_TOKEN_LIMIT
        )
        if not pieces:
            _mark_error(chunk, spec, "empty_text")
            skipped += 1
            continue

        chunk.content = pieces[0].content
        chunk.token_count = pieces[0].token_count
        if not _matches(chunk, spec):
            chunk.embedding = None
            chunk.embedding_provider = None
            chunk.embedding_model = None
            chunk.embedding_dimensions = None
        _clear_error(chunk)
        work.append(WorkItem(chunk, memory, pieces[0].content, pieces[0].token_count))

        if len(pieces) > 1:
            memory_key = str(memory.id)
            if memory_key not in next_indices:
                next_indices[memory_key] = max(
                    row.chunk_index for row, row_memory in rows if row_memory.id == memory.id
                ) + 1
            for piece in pieces[1:]:
                new_chunk = MemoryChunk(
                    memory_id=memory.id,
                    chunk_index=next_indices[memory_key],
                    content=piece.content,
                    token_count=piece.token_count,
                    metadata_json=chunk.metadata_json,
                )
                next_indices[memory_key] += 1
                db.add(new_chunk)
                work.append(WorkItem(new_chunk, memory, piece.content, piece.token_count))
                total += 1

    db.commit()

    newly_embedded = 0
    errors = 0
    for batch in _bounded_batches(work):
        try:
            result = create_embedding_batch_for_spec(
                [item.text for item in batch], task_type="RETRIEVAL_DOCUMENT", spec=spec
            )
            _apply_success(db, batch, result.vectors, result.spec)
            newly_embedded += len(batch)
        except Exception as exc:
            category, _permanent = provider_error_category(exc)
            if category == "bad_request" and len(batch) > 1:
                for item in batch:
                    added, failed = _embed_one_after_bad_batch(db, item, spec, report)
                    newly_embedded += added
                    errors += failed
                continue
            for item in batch:
                if _permanent:
                    _mark_error(item.chunk, spec, category)
                report(_safe_error(item, category, len(batch)))
                errors += 1
            db.commit()

    remaining = (
        db.query(MemoryChunk)
        .join(Memory, Memory.id == MemoryChunk.memory_id)
        .filter(Memory.user_id == user_id, Memory.source == source)
        .filter(
            or_(
                MemoryChunk.embedding.is_(None),
                MemoryChunk.embedding_provider.is_distinct_from(spec.provider),
                MemoryChunk.embedding_model.is_distinct_from(spec.model),
                MemoryChunk.embedding_dimensions.is_distinct_from(spec.dimensions),
            )
        )
        .count()
    )
    return {
        "total": total,
        "already_embedded": already_embedded,
        "newly_embedded": newly_embedded,
        "skipped": skipped,
        "remaining": remaining,
        "errors": errors,
        "embedding_signature": {
            "provider": spec.provider,
            "model": spec.model,
            "dimensions": spec.dimensions,
        },
    }
