from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Memory, MemoryChunk
from app.services.chunking import chunk_text
from app.services.ai_provider import (
    AIProviderNotConfigured,
    EmbeddingSpec,
    create_embedding_batch,
)


def index_memory(db: Session, memory: Memory, *, embed: bool = True) -> dict:
    chunks = chunk_text(memory.content)
    db.query(MemoryChunk).filter(MemoryChunk.memory_id == memory.id).delete(synchronize_session=False)

    embeddings: list[list[float] | None]
    embedding_specs: list[EmbeddingSpec | None] = [None] * len(chunks)
    embedding_error: str | None = None
    if embed and chunks:
        embeddings = [None] * len(chunks)
        current: list[int] = []
        current_tokens = 0
        batches: list[list[int]] = []
        for index, chunk in enumerate(chunks):
            if current and (
                len(current) >= settings.GEMINI_EMBEDDING_BATCH_SIZE
                or current_tokens + chunk.token_count > settings.GEMINI_EMBEDDING_BATCH_TOKEN_LIMIT
            ):
                batches.append(current)
                current = []
                current_tokens = 0
            current.append(index)
            current_tokens += chunk.token_count
        if current:
            batches.append(current)
        for positions in batches:
            try:
                batch = create_embedding_batch(
                    [chunks[index].content for index in positions],
                    task_type="RETRIEVAL_DOCUMENT",
                )
                for index, vector in zip(positions, batch.vectors, strict=True):
                    embeddings[index] = vector
                    embedding_specs[index] = batch.spec
            except AIProviderNotConfigured:
                break
            except Exception as exc:
                # Keep later batches indexable and never expose provider details.
                embedding_error = type(exc).__name__
    else:
        embeddings = [None] * len(chunks)

    base_metadata = {
        "source": memory.source,
        "source_id": memory.source_id,
        "title": memory.title,
        "event_type": memory.event_type,
        "event_date": memory.event_date.isoformat(),
        "file_url": memory.file_url,
        **(memory.metadata_json or {}),
    }
    for chunk, embedding, embedding_spec in zip(chunks, embeddings, embedding_specs, strict=True):
        db.add(MemoryChunk(
            memory_id=memory.id,
            chunk_index=chunk.index,
            content=chunk.content,
            token_count=chunk.token_count,
            metadata_json=base_metadata,
            embedding=embedding,
            embedding_provider=embedding_spec.provider if embedding is not None and embedding_spec else None,
            embedding_model=embedding_spec.model if embedding is not None and embedding_spec else None,
            embedding_dimensions=embedding_spec.dimensions if embedding is not None and embedding_spec else None,
        ))
    used_specs = {spec for spec in embedding_specs if spec is not None}
    summary_spec = next(iter(used_specs)) if len(used_specs) == 1 else None
    return {
        "chunks": len(chunks),
        "embedded": sum(vector is not None for vector in embeddings),
        "embedding_provider": summary_spec.provider if summary_spec else None,
        "embedding_model": summary_spec.model if summary_spec else None,
        "embedding_dimensions": summary_spec.dimensions if summary_spec else None,
        "embedding_error": embedding_error,
    }
