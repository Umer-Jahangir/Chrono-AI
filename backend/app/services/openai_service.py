"""Compatibility wrappers for older imports; new code uses ai_provider directly."""

from app.services.ai_provider import (
    AIProviderNotConfigured,
    answer_with_context,
    create_embedding_batch,
    get_openai_client,
)


OpenAINotConfigured = AIProviderNotConfigured


def create_embeddings(texts: list[str]) -> list[list[float]]:
    return create_embedding_batch(texts, task_type="RETRIEVAL_DOCUMENT").vectors
