from dataclasses import dataclass
from functools import lru_cache
import unicodedata

import tiktoken

from app.core.config import settings


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    token_count: int


@lru_cache(maxsize=1)
def _encoding():
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def normalize_embedding_text(text: str) -> str:
    """Return valid UTF-8 text without unsafe control characters."""
    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.encode("utf-8", errors="replace").decode("utf-8")
    normalized = "".join(
        character
        if character in "\n\r\t" or unicodedata.category(character) != "Cc"
        else " "
        for character in normalized
    )
    return normalized.strip()


def estimate_tokens(text: str) -> int:
    encoding = _encoding()
    if encoding is not None:
        return len(encoding.encode(text))
    return max(1, (len(text) + 3) // 4) if text else 0


def split_for_embedding(text: str, *, token_limit: int) -> list[TextChunk]:
    """Normalize text and split below the provider limit with a safety margin."""
    normalized = normalize_embedding_text(text)
    if not normalized:
        return []
    safe_limit = max(1, token_limit - min(128, max(1, token_limit // 16)))
    if estimate_tokens(normalized) <= safe_limit:
        return [TextChunk(index=0, content=normalized, token_count=estimate_tokens(normalized))]
    overlap = min(settings.CHUNK_OVERLAP_TOKENS, max(0, safe_limit - 1))
    return chunk_text(normalized, chunk_size=safe_limit, overlap=overlap)


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[TextChunk]:
    text = normalize_embedding_text(text)
    size = chunk_size or settings.CHUNK_SIZE_TOKENS
    shared = overlap if overlap is not None else settings.CHUNK_OVERLAP_TOKENS
    if size <= 0 or shared < 0 or shared >= size:
        raise ValueError("Chunk size must be positive and overlap must be smaller than chunk size")
    if not text.strip():
        return []

    encoding = _encoding()
    if encoding is not None:
        tokens: list[int] | list[str] = encoding.encode(text)
        decode = encoding.decode
    else:
        # The first tiktoken use may need its vocabulary download. Keep Drive
        # ingestion operational in offline environments with a word fallback.
        tokens = text.split()
        decode = lambda values: " ".join(values)
    step = size - shared
    chunks: list[TextChunk] = []
    for start in range(0, len(tokens), step):
        token_slice = tokens[start : start + size]
        if not token_slice:
            break
        content = decode(token_slice).strip()
        if content:
            chunks.append(TextChunk(index=len(chunks), content=content, token_count=len(token_slice)))
        if start + size >= len(tokens):
            break
    return chunks
