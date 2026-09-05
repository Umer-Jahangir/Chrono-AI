import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.core.config import settings
from app.services import ai_provider
from app.services.ai_provider import EmbeddingBatch, EmbeddingSpec


class GeminiProviderTests(unittest.TestCase):
    def tearDown(self):
        ai_provider.get_gemini_client.cache_clear()
        ai_provider.get_openai_client.cache_clear()

    def test_gemini_embedding_uses_exact_dimensions_and_task_types(self):
        model_api = Mock()
        model_api.embed_content.return_value = SimpleNamespace(
            embeddings=[SimpleNamespace(values=[2.0] + [0.0] * 1535)]
        )
        client = SimpleNamespace(models=model_api)
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch.object(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
            patch.object(settings, "GEMINI_EMBEDDING_DIMENSIONS", 1536),
            patch.object(settings, "OPENAI_API_KEY", ""),
            patch("app.services.ai_provider.get_gemini_client", return_value=client),
        ):
            document = ai_provider.create_embedding_batch(
                ["harmless test document"], task_type="RETRIEVAL_DOCUMENT"
            )
            query = ai_provider.create_embedding_batch(
                ["harmless test query"], task_type="RETRIEVAL_QUERY"
            )

        self.assertEqual(document.spec, EmbeddingSpec("gemini", "gemini-embedding-001", 1536))
        self.assertEqual(len(document.vectors[0]), 1536)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in document.vectors[0])), 1.0)
        calls = model_api.embed_content.call_args_list
        self.assertEqual(calls[0].kwargs["config"].output_dimensionality, 1536)
        self.assertEqual(calls[0].kwargs["config"].task_type, "RETRIEVAL_DOCUMENT")
        self.assertIsNone(calls[0].kwargs["config"].auto_truncate)
        self.assertEqual(calls[1].kwargs["config"].task_type, "RETRIEVAL_QUERY")
        self.assertEqual(query.spec, document.spec)

    def test_gemini_is_primary_for_grounded_generation(self):
        model_api = Mock()
        model_api.generate_content.return_value = SimpleNamespace(text="Supported answer [1]")
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch.object(settings, "GEMINI_CHAT_MODEL", "gemini-test-chat"),
            patch.object(settings, "OPENAI_API_KEY", "fallback-key"),
            patch("app.services.ai_provider.get_gemini_client", return_value=SimpleNamespace(models=model_api)),
            patch("app.services.ai_provider._openai_answer") as openai_answer,
        ):
            answer = ai_provider.answer_with_context("Question?", "[1] Safe fixture context")

        self.assertEqual(answer, "Supported answer [1]")
        openai_answer.assert_not_called()
        call = model_api.generate_content.call_args
        self.assertEqual(call.kwargs["model"], "gemini-test-chat")
        self.assertTrue(call.kwargs["config"].automatic_function_calling.disable)
        self.assertNotIn("test-key", repr(call))

    def test_provider_outage_falls_back_to_openai_with_actual_signature(self):
        fallback = EmbeddingBatch(
            vectors=[[1.0] + [0.0] * 1535],
            spec=EmbeddingSpec("openai", "fallback-model", 1536),
        )
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch.object(settings, "OPENAI_API_KEY", "fallback-key"),
            patch("app.services.ai_provider._gemini_embeddings", side_effect=RuntimeError("429")),
            patch("app.services.ai_provider._openai_embeddings", return_value=fallback),
        ):
            result = ai_provider.create_embedding_batch(["safe fixture"], task_type="RETRIEVAL_QUERY")
        self.assertEqual(result.spec.provider, "openai")

    def test_generation_outage_falls_back_to_openai(self):
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch.object(settings, "GEMINI_CHAT_MODEL", "gemini-test-chat"),
            patch.object(settings, "OPENAI_API_KEY", "fallback-key"),
            patch("app.services.ai_provider._gemini_answer", side_effect=RuntimeError("429")),
            patch("app.services.ai_provider._openai_answer", return_value="Fallback answer [1]") as fallback,
        ):
            answer = ai_provider.answer_with_context("Question?", "[1] Safe fixture")
        self.assertEqual(answer, "Fallback answer [1]")
        fallback.assert_called_once()

    def test_gemini_client_uses_single_sdk_attempt_and_bounded_timeout(self):
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch.object(settings, "GEMINI_TIMEOUT_SECONDS", 17),
            patch.object(settings, "GEMINI_MAX_ATTEMPTS", 3),
            patch("google.genai.Client") as client_class,
        ):
            ai_provider.get_gemini_client.cache_clear()
            ai_provider.get_gemini_client()
        options = client_class.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, 15000)
        self.assertEqual(options.retry_options.attempts, 1)
        self.assertIn(429, options.retry_options.http_status_codes)

    def test_transient_generation_errors_retry_at_most_twice(self):
        transient = RuntimeError("redacted")
        transient.status_code = 503
        with (
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch.object(settings, "GEMINI_CHAT_MODEL", "gemini-test-chat"),
            patch.object(settings, "OPENAI_API_KEY", ""),
            patch.object(settings, "GEMINI_MAX_ATTEMPTS", 2),
            patch("app.services.ai_provider._gemini_answer", side_effect=transient) as generate,
            patch("app.services.ai_provider.time.sleep"),
            patch("app.services.ai_provider.random.uniform", return_value=0),
        ):
            with self.assertRaises(ai_provider.AIProviderUnavailable):
                ai_provider.answer_with_context("Question?", "[1] Safe fixture")
        self.assertEqual(generate.call_count, 2)

    def test_permanent_generation_errors_are_not_retried(self):
        for status_code in (400, 401, 403, 404):
            permanent = RuntimeError("redacted")
            permanent.status_code = status_code
            with self.subTest(status_code=status_code):
                with (
                    patch.object(settings, "GEMINI_API_KEY", "test-key"),
                    patch.object(settings, "GEMINI_CHAT_MODEL", "gemini-test-chat"),
                    patch.object(settings, "OPENAI_API_KEY", ""),
                    patch("app.services.ai_provider._gemini_answer", side_effect=permanent) as generate,
                ):
                    with self.assertRaises(ai_provider.AIProviderUnavailable):
                        ai_provider.answer_with_context("Question?", "[1] Safe fixture")
                    self.assertEqual(generate.call_count, 1)


@unittest.skipUnless(settings.GEMINI_API_KEY, "GEMINI_API_KEY is not configured")
class GeminiLiveTests(unittest.TestCase):
    def test_live_embedding_returns_1536_dimensions(self):
        ai_provider.get_gemini_client.cache_clear()
        result = ai_provider.create_embedding_batch(
            ["Chrono optional live embedding test fixture"],
            task_type="RETRIEVAL_DOCUMENT",
        )
        self.assertEqual(result.spec.provider, "gemini")
        self.assertEqual(result.spec.dimensions, 1536)
        self.assertEqual(len(result.vectors[0]), 1536)


if __name__ == "__main__":
    unittest.main()
