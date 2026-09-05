import json
import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import engine, get_db
from app.db.models import Memory, MemoryChunk
from app.main import app
from app.services.auth import get_current_user
from app.api.google_drive import resolve_n8n_owner
from app.services.memory_indexer import index_memory
from app.services.ai_provider import AIProviderNotConfigured, EmbeddingBatch, EmbeddingSpec
from app.services.retrieval import hybrid_search


def vector(axis: int) -> list[float]:
    result = [0.0] * 1536
    result[axis] = 1.0
    return result


def cosine_vector(primary_axis: int, similarity: float, secondary_axis: int) -> list[float]:
    result = [0.0] * 1536
    result[primary_axis] = similarity
    result[secondary_axis] = (1.0 - similarity * similarity) ** 0.5
    return result


class RetrievalEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = engine.connect()
        cls.transaction = cls.connection.begin()
        cls.db = Session(bind=cls.connection, join_transaction_mode="create_savepoint")
        suffix = uuid.uuid4().hex
        cls.user_a = f"chrono-e2e-a-{suffix}"
        cls.user_b = f"chrono-e2e-b-{suffix}"
        cls.source = f"fixture-{suffix}"

        cls.feline = cls._memory(
            user_id=cls.user_a,
            source_id=f"feline-{suffix}",
            title="Feline Care Guide",
            content="Whiskers purrs when comfortable and needs exactly 55 grams of food each day.",
            event_type="created",
            event_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
            mime_type="text/plain",
            file_url="https://example.invalid/feline-care",
        )
        cls.vehicle = cls._memory(
            user_id=cls.user_a,
            source_id=f"vehicle-{suffix}",
            title="Vehicle Maintenance Guide",
            content="Schedule an oil change every 8,000 kilometres to maintain the vehicle.",
            event_type="modified",
            event_date=datetime(2025, 5, 20, tzinfo=timezone.utc),
            mime_type="application/pdf",
            file_url="https://example.invalid/vehicle-maintenance",
        )
        cls.private = cls._memory(
            user_id=cls.user_b,
            source_id=f"private-{suffix}",
            title="Other User Record",
            content="privateisolationtoken belongs only to user B.",
            event_type="created",
            event_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
            mime_type="text/plain",
            file_url="https://example.invalid/private",
        )
        cls.war = cls._memory(
            user_id=cls.user_a,
            source_id=f"war-{suffix}",
            title="War and Digital Trauma Study",
            content=(
                "The study reports that exposure to graphic war coverage causes digital trauma "
                "among Gen Z. Repeated viewing of violent conflict can intensify distress."
            ),
            event_type="created",
            event_date=datetime(2026, 3, 5, tzinfo=timezone.utc),
            mime_type="application/pdf",
            file_url="https://example.invalid/war-study",
        )
        cls.multi = cls._memory(
            user_id=cls.user_a,
            source_id=f"multi-{suffix}",
            title="Multi Chunk Fixture",
            content="groupingmarker",
            event_type="created",
            event_date=datetime(2026, 3, 6, tzinfo=timezone.utc),
            mime_type="text/plain",
            file_url="https://example.invalid/multi",
        )
        cls.db.flush()
        for memory in (cls.feline, cls.vehicle, cls.private, cls.war):
            index_memory(cls.db, memory, embed=False)
        for index in range(4):
            cls.db.add(MemoryChunk(
                memory_id=cls.multi.id,
                chunk_index=index,
                content=f"groupingmarker passage number {index} " + ("detail " * 80),
                token_count=84,
                metadata_json={"mime_type": "text/plain", "fixture": True},
            ))
        cls.db.flush()

        signature = {
            MemoryChunk.embedding_provider: "fake",
            MemoryChunk.embedding_model: "fake-v1",
            MemoryChunk.embedding_dimensions: 1536,
        }
        cls.db.query(MemoryChunk).filter(MemoryChunk.memory_id == cls.feline.id).update({MemoryChunk.embedding: vector(0), **signature})
        cls.db.query(MemoryChunk).filter(MemoryChunk.memory_id == cls.vehicle.id).update({MemoryChunk.embedding: vector(1), **signature})
        cls.db.query(MemoryChunk).filter(MemoryChunk.memory_id == cls.private.id).update({MemoryChunk.embedding: vector(2), **signature})
        cls.db.flush()

        def override_db():
            yield cls.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=cls.user_a)
        app.dependency_overrides[resolve_n8n_owner] = lambda: cls.user_a
        cls.client = TestClient(app)

    @classmethod
    def _memory(cls, *, user_id, source_id, title, content, event_type, event_date, mime_type, file_url):
        memory = Memory(
            user_id=user_id,
            source=cls.source,
            source_id=source_id,
            title=title,
            content=content,
            event_type=event_type,
            event_date=event_date,
            file_url=file_url,
            metadata_json={"mime_type": mime_type, "fixture": True},
        )
        cls.db.add(memory)
        cls.db.flush()
        return memory

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.client.close()
        cls.db.close()
        cls.transaction.rollback()
        cls.connection.close()
        engine.dispose()

    def no_provider(self, *_args, **_kwargs):
        raise AIProviderNotConfigured("test: no provider")

    def fake_embeddings(self, texts, **_kwargs):
        vectors = []
        for text in texts:
            lowered = text.lower()
            if any(term in lowered for term in ("household pet", "vibrating sound", "whiskers", "feline")):
                vectors.append(vector(0))
            elif any(term in lowered for term in ("automobile", "lubricant", "oil change", "vehicle")):
                vectors.append(vector(1))
            else:
                vectors.append(vector(2))
        return EmbeddingBatch(vectors, EmbeddingSpec("fake", "fake-v1", 1536))

    def search(self, query, **params):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.no_provider):
            return self.client.get("/search", params={"q": query, **params})

    def test_exact_keyword_retrieval(self):
        feline = self.search("Whiskers")
        vehicle = self.search("8,000 kilometres")
        self.assertEqual(feline.status_code, 200)
        self.assertEqual(feline.json()["results"][0]["title"], "Feline Care Guide")
        self.assertEqual(vehicle.json()["results"][0]["title"], "Vehicle Maintenance Guide")
        first = feline.json()["results"][0]
        print("REDACTED_SEARCH_RESPONSE", {
            "query": feline.json()["query"],
            "mode": feline.json()["mode"],
            "count": feline.json()["count"],
            "top_result": {
                "title": first["title"],
                "excerpt": first["excerpt"],
            },
        })

    def test_natural_language_war_question_and_medication_gap(self):
        found = self.search("What causes digital trauma among Gen Z?", source=self.source)
        self.assertEqual(found.status_code, 200)
        self.assertGreater(found.json()["count"], 0)
        self.assertEqual(found.json()["results"][0]["title"], "War and Digital Trauma Study")

        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.no_provider):
            unsupported_search = self.client.get("/search", params={
                "q": "What medication treats digital trauma?",
                "source": self.source,
            })
            unsupported = self.client.post("/ask", json={
                "question": "What medication treats digital trauma?",
                "source": self.source,
            })
        self.assertEqual(unsupported.status_code, 200)
        self.assertEqual(unsupported_search.json()["count"], 0)
        self.assertIn("not have enough information", unsupported.json()["answer"])
        self.assertEqual(unsupported.json()["sources"], [])

    def test_results_are_grouped_and_public_shape_is_sanitized(self):
        response = self.search("groupingmarker", source=self.source, limit=10)
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["count"], 2)
        for result in body["results"]:
            self.assertLessEqual(len(result["excerpt"]), 281)
            self.assertFalse({
                "content", "metadata", "memory_id", "chunk_id", "source_id", "file_url"
            }.intersection(result))

    def test_metadata_date_and_mime_filters(self):
        self.assertEqual(self.search("Whiskers", source=self.source).json()["count"], 1)
        self.assertEqual(self.search("Whiskers", source="wrong-source").json()["count"], 0)
        self.assertEqual(self.search("Whiskers", event_type="created").json()["count"], 1)
        self.assertEqual(self.search("Whiskers", event_type="modified").json()["count"], 0)
        self.assertEqual(self.search("oil change", start="2026-01-01T00:00:00Z").json()["count"], 0)
        self.assertEqual(self.search("oil change", end="2025-12-31T23:59:59Z").json()["count"], 1)
        self.assertEqual(self.search("Whiskers", mime_type="text/plain").json()["count"], 1)
        self.assertEqual(self.search("Whiskers", mime_type="application/pdf").json()["count"], 0)

    def test_extractive_ask_facts_and_citation(self):
        with (
            patch("app.services.retrieval.create_embedding_batch", side_effect=self.no_provider),
            patch("app.api.ask.answer_with_context", side_effect=AIProviderNotConfigured("test: no provider")),
        ):
            response = self.client.post("/ask", json={
                "question": "Whiskers purrs 55 grams",
                "source": self.source,
            })
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["retrieval_mode"], "lexical-extractive")
        self.assertIn("purrs", body["answer"])
        self.assertIn("55 grams", body["answer"])
        self.assertIn("[1]", body["answer"])
        self.assertEqual(body["sources"][0]["title"], "Feline Care Guide")
        self.assertFalse({"source_id", "file_url", "chunk_index"}.intersection(body["sources"][0]))
        print("REDACTED_ASK_RESPONSE", {
            "answer": body["answer"],
            "retrieval_mode": body["retrieval_mode"],
            "sources": [{
                "citation": body["sources"][0]["citation"],
                "title": body["sources"][0]["title"],
                "excerpt": body["sources"][0]["excerpt"],
            }],
        })

    def test_unsupported_question_reports_insufficient_evidence(self):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.no_provider):
            response = self.client.post("/ask", json={
                "question": "orbital period Neptune astronomy",
                "source": self.source,
            })
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("not have enough information", body["answer"])
        self.assertEqual(body["sources"], [])

    def test_unsupported_question_with_keyword_overlap_is_rejected(self):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.no_provider):
            response = self.client.post("/ask", json={
                "question": "What color is Whiskers?",
                "source": self.source,
            })
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("not have enough information", body["answer"])
        self.assertEqual(body["sources"], [])

    def test_semantic_unsupported_question_reports_insufficient_evidence(self):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_embeddings):
            response = self.client.post("/ask", json={
                "question": "orbital period Neptune astronomy",
                "user_id": self.user_a,
                "source": self.source,
            })
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("not have enough information", body["answer"])
        self.assertEqual(body["sources"], [])

    def test_user_isolation(self):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.no_provider):
            denied = self.client.get("/search", params={"user_id": self.user_b, "q": "privateisolationtoken"})
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=self.user_b)
            try:
                allowed = self.client.get("/search", params={"q": "privateisolationtoken"})
            finally:
                app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=self.user_a)
        self.assertEqual(denied.json()["count"], 0)
        self.assertEqual(allowed.json()["count"], 1)

    def test_fake_semantic_pipeline_metrics(self):
        cases = [
            ("household pet that makes a vibrating sound", "Feline Care Guide"),
            ("automobile lubricant replacement interval", "Vehicle Maintenance Guide"),
        ]
        reciprocal_ranks = []
        hit_at_1 = 0
        hit_at_3 = 0
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_embeddings):
            for query, expected in cases:
                results, mode = hybrid_search(
                    self.db, user_id=self.user_a, query_text=query, limit=3, source=self.source
                )
                titles = [result["title"] for result in results]
                self.assertEqual(mode, "hybrid")
                rank = titles.index(expected) + 1
                hit_at_1 += int(rank <= 1)
                hit_at_3 += int(rank <= 3)
                reciprocal_ranks.append(1 / rank)
            mixed, mixed_mode = hybrid_search(
                self.db,
                user_id=self.user_a,
                query_text="Whiskers purrs",
                limit=3,
                source=self.source,
            )
            filtered, _ = hybrid_search(
                self.db,
                user_id=self.user_a,
                query_text="household pet that makes a vibrating sound",
                limit=3,
                source=self.source,
                mime_type="application/pdf",
            )
            self.assertEqual(mixed_mode, "hybrid")
            self.assertEqual(mixed[0]["title"], "Feline Care Guide")
            self.assertEqual(filtered, [])
        metrics = {
            "hit_at_1": hit_at_1 / len(cases),
            "hit_at_3": hit_at_3 / len(cases),
            "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks),
        }
        print("FAKE_SEMANTIC_METRICS", metrics)
        self.assertEqual(metrics, {"hit_at_1": 1.0, "hit_at_3": 1.0, "mrr": 1.0})

    def test_semantic_candidate_below_absolute_relevance_is_not_returned(self):
        batch = EmbeddingBatch(
            [cosine_vector(0, 0.70, 7)], EmbeddingSpec("fake", "fake-v1", 1536)
        )
        diagnostics = {}
        with patch("app.services.retrieval.create_embedding_batch", return_value=batch):
            results, mode = hybrid_search(
                self.db, user_id=self.user_a, query_text="domestic companion resonance",
                limit=3, source=self.source, diagnostics=diagnostics,
            )
        self.assertEqual(mode, "hybrid")
        self.assertEqual(results, [])
        self.assertGreater(diagnostics["candidate_count"], 0)
        self.assertEqual(diagnostics["accepted_file_count"], 0)

    def test_strong_lexical_match_outranks_loose_semantic_candidate(self):
        batch = EmbeddingBatch(
            [cosine_vector(1, 0.80, 7)], EmbeddingSpec("fake", "fake-v1", 1536)
        )
        with patch("app.services.retrieval.create_embedding_batch", return_value=batch):
            results, _mode = hybrid_search(
                self.db, user_id=self.user_a, query_text="Whiskers", limit=3,
                source=self.source,
            )
        self.assertEqual(results[0]["title"], "Feline Care Guide")

    def test_file_score_uses_bounded_supporting_passages(self):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.no_provider):
            results, _mode = hybrid_search(
                self.db, user_id=self.user_a, query_text="groupingmarker",
                limit=10, source=self.source,
            )
        grouped = [result for result in results if result["title"] == "Multi Chunk Fixture"]
        self.assertEqual(len(grouped), 2)
        self.assertEqual(len({result["score"] for result in grouped}), 1)
        self.assertLessEqual(grouped[0]["score"], 1.0)

    def test_semantic_query_does_not_mix_embedding_signatures(self):
        chunks = self.db.query(MemoryChunk).filter(MemoryChunk.memory_id == self.feline.id).all()
        try:
            for chunk in chunks:
                chunk.embedding_provider = "different-provider"
            self.db.flush()
            with patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_embeddings):
                results, _ = hybrid_search(
                    self.db,
                    user_id=self.user_a,
                    query_text="household pet that makes a vibrating sound",
                    limit=3,
                    source=self.source,
                )
            self.assertNotIn("Feline Care Guide", [result["title"] for result in results])
        finally:
            for chunk in chunks:
                chunk.embedding_provider = "fake"
            self.db.flush()

    def test_indexer_persists_embedding_signature(self):
        memory = self._memory(
            user_id=self.user_a,
            source_id=f"signature-{uuid.uuid4().hex}",
            title="Embedding Signature Fixture",
            content="Safe deterministic signature fixture.",
            event_type="created",
            event_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
            mime_type="text/plain",
            file_url="https://example.invalid/signature",
        )
        batch = EmbeddingBatch([vector(3)], EmbeddingSpec("gemini", "gemini-embedding-001", 1536))
        with patch("app.services.memory_indexer.create_embedding_batch", return_value=batch):
            stats = index_memory(self.db, memory)
        self.db.flush()
        chunk = self.db.query(MemoryChunk).filter_by(memory_id=memory.id).one()
        self.assertEqual(stats["embedding_provider"], "gemini")
        self.assertEqual(chunk.embedding_provider, "gemini")
        self.assertEqual(chunk.embedding_model, "gemini-embedding-001")
        self.assertEqual(chunk.embedding_dimensions, 1536)

    def test_lifecycle_create_modify_delete_cascades(self):
        file_id = f"lifecycle-{uuid.uuid4().hex}"
        event = {
            "source": "google_drive",
            "drive_id": "test-drive",
            "change_id": f"create-{uuid.uuid4().hex}",
            "event_type": "created",
            "file_id": file_id,
            "name": "Lifecycle Fixture.txt",
            "mime_type": "text/plain",
            "is_folder": False,
            "removed": False,
            "occurred_at": "2026-03-01T00:00:00Z",
            "parents": ["test-parent"],
            "previous_parents": [],
            "web_view_link": "https://example.invalid/lifecycle",
            "owners": [],
            "raw_change": {"fixture": True},
        }
        headers = {"X-N8N-Secret": settings.N8N_WEBHOOK_SECRET}
        created = self.client.post(
            "/integrations/google-drive/content",
            data={"event_json": json.dumps(event)},
            files={"file": ("Lifecycle Fixture.txt", b"olduniquetoken initial content", "text/plain")},
            headers=headers,
        )
        self.assertEqual(created.status_code, 200)
        memory = self.db.query(Memory).filter_by(source="google_drive", source_id=file_id).one()
        self.assertGreater(self.db.query(MemoryChunk).filter_by(memory_id=memory.id).count(), 0)

        event["event_type"] = "modified"
        event["change_id"] = f"modify-{uuid.uuid4().hex}"
        modified = self.client.post(
            "/integrations/google-drive/content",
            data={"event_json": json.dumps(event)},
            files={"file": ("Lifecycle Fixture.txt", b"newuniquetoken replacement content", "text/plain")},
            headers=headers,
        )
        self.assertEqual(modified.status_code, 200)
        chunks = self.db.query(MemoryChunk).filter_by(memory_id=memory.id).all()
        self.assertTrue(any("newuniquetoken" in chunk.content for chunk in chunks))
        self.assertFalse(any("olduniquetoken" in chunk.content for chunk in chunks))

        event["event_type"] = "trashed"
        event["change_id"] = f"trash-{uuid.uuid4().hex}"
        trashed = self.client.post("/integrations/google-drive/events", json=event, headers=headers)
        self.assertEqual(trashed.status_code, 200)
        self.db.expire_all()
        self.assertEqual(self.db.query(Memory).filter_by(source="google_drive", source_id=file_id).count(), 1)
        self.assertEqual(self.db.query(MemoryChunk).filter_by(memory_id=memory.id).count(), 0)

        event["event_type"] = "deleted"
        event["removed"] = True
        event["change_id"] = f"delete-{uuid.uuid4().hex}"
        deleted = self.client.post("/integrations/google-drive/events", json=event, headers=headers)
        self.assertEqual(deleted.status_code, 200)
        self.db.expire_all()
        self.assertEqual(self.db.query(Memory).filter_by(source="google_drive", source_id=file_id).count(), 0)


if __name__ == "__main__":
    unittest.main()
