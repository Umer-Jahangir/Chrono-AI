from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
import logging
import math
import random
import time
from typing import Literal

from openai import OpenAI

from app.core.config import settings


EmbeddingTask = Literal["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]
_VECTOR_DIMENSIONS = 1536
_RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504]
logger = logging.getLogger(__name__)


class AIProviderNotConfigured(RuntimeError):
    pass


class AIProviderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingSpec:
    provider: str
    model: str
    dimensions: int


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    spec: EmbeddingSpec


def preferred_embedding_spec() -> EmbeddingSpec | None:
    if settings.GEMINI_API_KEY:
        return EmbeddingSpec(
            provider="gemini",
            model=settings.GEMINI_EMBEDDING_MODEL,
            dimensions=settings.GEMINI_EMBEDDING_DIMENSIONS,
        )
    if settings.OPENAI_API_KEY and settings.OPENAI_CHAT_MODEL:
        return EmbeddingSpec(
            provider="openai",
            model=settings.OPENAI_EMBEDDING_MODEL,
            dimensions=_VECTOR_DIMENSIONS,
        )
    return None


def preferred_generation_provider() -> dict[str, str] | None:
    if settings.GEMINI_API_KEY and settings.GEMINI_CHAT_MODEL:
        return {"provider": "gemini", "model": settings.GEMINI_CHAT_MODEL}
    if settings.OPENAI_API_KEY:
        return {"provider": "openai", "model": settings.OPENAI_CHAT_MODEL}
    return None


@lru_cache
def get_gemini_client():
    if not settings.GEMINI_API_KEY:
        raise AIProviderNotConfigured("Gemini is not configured")
    from google import genai
    from google.genai import types

    retry_options = types.HttpRetryOptions(
        attempts=1,
        initial_delay=0.5,
        max_delay=4.0,
        exp_base=2.0,
        http_status_codes=_RETRYABLE_STATUS_CODES,
    )
    return genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options=types.HttpOptions(
            timeout=max(1, min(settings.GEMINI_TIMEOUT_SECONDS, 15)) * 1000,
            retry_options=retry_options,
        ),
    )


@lru_cache
def get_openai_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise AIProviderNotConfigured("OpenAI is not configured")
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.GEMINI_TIMEOUT_SECONDS,
        max_retries=max(0, settings.GEMINI_MAX_ATTEMPTS - 1),
    )


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        raise AIProviderUnavailable("Embedding provider returned a zero vector")
    return [value / magnitude for value in vector]


def _gemini_embeddings(texts: list[str], task_type: EmbeddingTask) -> EmbeddingBatch:
    if settings.GEMINI_EMBEDDING_DIMENSIONS != _VECTOR_DIMENSIONS:
        raise AIProviderUnavailable("Gemini embedding dimensions must be exactly 1536")
    from google.genai import types

    response = get_gemini_client().models.embed_content(
        model=settings.GEMINI_EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=_VECTOR_DIMENSIONS,
        ),
    )
    vectors = [_normalize(list(item.values)) for item in response.embeddings]
    if len(vectors) != len(texts) or any(len(vector) != _VECTOR_DIMENSIONS for vector in vectors):
        raise AIProviderUnavailable("Gemini returned an invalid embedding response")
    return EmbeddingBatch(
        vectors=vectors,
        spec=EmbeddingSpec("gemini", settings.GEMINI_EMBEDDING_MODEL, _VECTOR_DIMENSIONS),
    )


def create_embedding_batch_for_spec(
    texts: list[str], *, task_type: EmbeddingTask, spec: EmbeddingSpec
) -> EmbeddingBatch:
    """Embed with one exact signature; reindexing must not fall through to another model."""
    if spec.dimensions != _VECTOR_DIMENSIONS:
        raise AIProviderUnavailable("Embedding dimensions must be exactly 1536")
    if spec.provider == "gemini":
        return _gemini_embeddings(texts, task_type)
    if spec.provider == "openai":
        return _openai_embeddings(texts)
    raise AIProviderUnavailable("Unsupported embedding provider")


def provider_error_category(exc: Exception) -> tuple[str, bool]:
    """Map provider errors without returning their potentially sensitive message."""
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 400:
        return "bad_request", True
    if code in {401, 403}:
        return "authentication", True
    if code == 404:
        return "model_not_found", True
    if code == 413:
        return "input_too_large", True
    if code == 429:
        return "rate_limited", False
    if code in {408, 500, 502, 503, 504}:
        return "transient_provider_error", False
    return "provider_error", False


def _status_code(exc: Exception) -> int | None:
    value = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_transient(exc: Exception) -> bool:
    code = _status_code(exc)
    if code is not None:
        return code in _RETRYABLE_STATUS_CODES or 500 <= code <= 599
    name = type(exc).__name__.casefold()
    return isinstance(exc, TimeoutError) or "timeout" in name or "deadline" in name


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) or getattr(exc, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    try:
        return max(0.0, min(float(value), settings.GEMINI_RETRY_MAX_DELAY_SECONDS))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(value))
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
            return max(0.0, min(seconds, settings.GEMINI_RETRY_MAX_DELAY_SECONDS))
        except (TypeError, ValueError, OverflowError):
            return None


def _gemini_generate_with_retry(question: str, context: str) -> str:
    started = time.monotonic()
    attempts = max(1, min(settings.GEMINI_MAX_ATTEMPTS, 2))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        attempt_started = time.monotonic()
        try:
            answer = _gemini_answer(question, context)
            logger.info(
                "chrono_ai provider=gemini operation=generation attempt=%d outcome=success duration_ms=%.2f",
                attempt, (time.monotonic() - attempt_started) * 1000,
            )
            return answer
        except Exception as exc:
            last_error = exc
            category, _ = provider_error_category(exc)
            elapsed = time.monotonic() - started
            logger.warning(
                "chrono_ai provider=gemini operation=generation attempt=%d outcome=failure category=%s status=%s duration_ms=%.2f",
                attempt, category, _status_code(exc) or "none",
                (time.monotonic() - attempt_started) * 1000,
            )
            if not _is_transient(exc) or attempt >= attempts:
                break
            delay = _retry_after(exc)
            if delay is None:
                delay = min(
                    settings.GEMINI_RETRY_INITIAL_DELAY_SECONDS * (2 ** (attempt - 1)),
                    settings.GEMINI_RETRY_MAX_DELAY_SECONDS,
                ) + random.uniform(0, 0.15)
            if elapsed + delay >= settings.GEMINI_GENERATION_BUDGET_SECONDS:
                break
            time.sleep(delay)
    raise AIProviderUnavailable("Gemini generation is temporarily unavailable") from last_error


def _openai_embeddings(texts: list[str]) -> EmbeddingBatch:
    response = get_openai_client().embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=texts,
        dimensions=_VECTOR_DIMENSIONS,
    )
    vectors = [list(item.embedding) for item in sorted(response.data, key=lambda item: item.index)]
    if len(vectors) != len(texts) or any(len(vector) != _VECTOR_DIMENSIONS for vector in vectors):
        raise AIProviderUnavailable("OpenAI returned an invalid embedding response")
    return EmbeddingBatch(
        vectors=vectors,
        spec=EmbeddingSpec("openai", settings.OPENAI_EMBEDDING_MODEL, _VECTOR_DIMENSIONS),
    )


def create_embedding_batch(texts: list[str], *, task_type: EmbeddingTask) -> EmbeddingBatch:
    if not texts:
        spec = preferred_embedding_spec()
        if spec is None:
            raise AIProviderNotConfigured("No AI embedding provider is configured")
        return EmbeddingBatch([], spec)

    failures: list[str] = []
    if settings.GEMINI_API_KEY:
        try:
            return _gemini_embeddings(texts, task_type)
        except Exception:
            failures.append("Gemini")
    if settings.OPENAI_API_KEY:
        try:
            return _openai_embeddings(texts)
        except Exception:
            failures.append("OpenAI")
    if not failures:
        raise AIProviderNotConfigured("No AI embedding provider is configured")
    raise AIProviderUnavailable(f"Configured embedding provider unavailable: {', '.join(failures)}")


_GROUNDING_INSTRUCTIONS = (
    "Answer only from the supplied Chrono memory context. "
    "If the context does not contain the answer, say that you do not have enough information. "
    "Cite supporting passages using [1], [2], and so on. Do not invent citations."
)


def _gemini_answer(question: str, context: str) -> str:
    if not settings.GEMINI_CHAT_MODEL:
        raise AIProviderNotConfigured("Gemini chat model is not configured")
    from google.genai import types

    response = get_gemini_client().models.generate_content(
        model=settings.GEMINI_CHAT_MODEL,
        contents=f"Question:\n{question}\n\nChrono memory context:\n{context}",
        config=types.GenerateContentConfig(
            system_instruction=_GROUNDING_INSTRUCTIONS,
            temperature=0.1,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    if not response.text:
        raise AIProviderUnavailable("Gemini returned an empty answer")
    return response.text


def _openai_answer(question: str, context: str) -> str:
    response = get_openai_client().responses.create(
        model=settings.OPENAI_CHAT_MODEL,
        store=False,
        instructions=_GROUNDING_INSTRUCTIONS,
        input=f"Question:\n{question}\n\nChrono memory context:\n{context}",
    )
    if not response.output_text:
        raise AIProviderUnavailable("OpenAI returned an empty answer")
    return response.output_text


def answer_with_context(question: str, context: str) -> str:
    failures: list[str] = []
    if settings.GEMINI_API_KEY and settings.GEMINI_CHAT_MODEL:
        try:
            return _gemini_generate_with_retry(question, context)
        except Exception:
            failures.append("Gemini")
    if settings.OPENAI_API_KEY and settings.OPENAI_CHAT_MODEL:
        try:
            return _openai_answer(question, context)
        except Exception:
            failures.append("OpenAI")
    if not failures:
        raise AIProviderNotConfigured("No AI answer-generation provider is configured")
    raise AIProviderUnavailable(f"Configured answer-generation provider unavailable: {', '.join(failures)}")
