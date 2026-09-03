import uuid
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.db.database import engine
from app.db.models import Memory, MemoryChunk
from app.services.ai_provider import EmbeddingBatch, EmbeddingSpec
from app.services.embedding_reindexer import reindex_embeddings


def vector() -> list[float]:
    return [1.0] + [0.0] * 1535


class FakeBadRequest(Exception):
    code = 400


class ResumableEmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(bind=self.connection, join_transaction_mode="create_savepoint")
        suffix = uuid.uuid4().hex
        self.user_id = f"reindex-user-{suffix}"
        self.source = f"reindex-source-{suffix}"
        self.memory = Memory(
            user_id=self.user_id,
            source=self.source,
            source_id=f"fixture-{suffix}",
            title="Safe Reindex Test Document",
            content="controlled fixture",
            event_type="created",
            event_date=datetime(2026, 8, 25, tzinfo=timezone.utc),
            metadata_json={"mime_type": "text/plain"},
        )
        self.db.add(self.memory)
        self.db.flush()
        contents = [
            "valid chunk before rejected input",
            "rejectmarker " + ("oversized " * 2500),
            "valid chunk after rejected input",
        ]
        for index, content in enumerate(contents):
            self.db.add(MemoryChunk(
                memory_id=self.memory.id,
                chunk_index=index,
                content=content,
                token_count=max(1, len(content.split())),
                metadata_json={},
            ))
        self.db.flush()
        self.spec = EmbeddingSpec("gemini", "gemini-embedding-001", 1536)

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def test_bad_oversized_item_is_isolated_and_next_run_resumes(self):
        calls: list[int] = []

        def embed(texts, **_kwargs):
            calls.append(len(texts))
            if any("rejectmarker" in text for text in texts):
                raise FakeBadRequest()
            return EmbeddingBatch([vector() for _text in texts], self.spec)

        reported: list[dict] = []
        with (
            patch("app.services.embedding_reindexer.preferred_embedding_spec", return_value=self.spec),
            patch("app.services.embedding_reindexer.create_embedding_batch_for_spec", side_effect=embed),
        ):
            first = reindex_embeddings(
                self.db,
                user_id=self.user_id,
                source=self.source,
                report=reported.append,
            )

        chunks = (
            self.db.query(MemoryChunk)
            .filter(MemoryChunk.memory_id == self.memory.id)
            .order_by(MemoryChunk.chunk_index)
            .all()
        )
        rejected = [chunk for chunk in chunks if "rejectmarker" in chunk.content]
        successful = [chunk for chunk in chunks if "rejectmarker" not in chunk.content]
        self.assertGreater(len(chunks), 3, "oversized input should have been split")
        self.assertEqual(first["errors"], 1)
        self.assertEqual(first["remaining"], 1)
        self.assertTrue(all(chunk.embedding is not None for chunk in successful))
        self.assertEqual(rejected[0].embedding_error_category, "bad_request")
        self.assertTrue(any(size > 1 for size in calls), "the failed batch should be isolated")
        self.assertEqual(reported[0]["error_category"], "bad_request")
        self.assertEqual(reported[0]["memory_title"], "Safe Reindex Test Document")
        self.assertEqual(reported[0]["batch_size"], 1)
        self.assertFalse({"content", "api_key", "metadata"}.intersection(reported[0]))

        with (
            patch("app.services.embedding_reindexer.preferred_embedding_spec", return_value=self.spec),
            patch("app.services.embedding_reindexer.create_embedding_batch_for_spec") as second_embed,
        ):
            second = reindex_embeddings(
                self.db,
                user_id=self.user_id,
                source=self.source,
            )

        second_embed.assert_not_called()
        self.assertEqual(second["newly_embedded"], 0)
        self.assertEqual(second["errors"], 0)
        self.assertEqual(second["skipped"], 1)
        self.assertEqual(second["remaining"], 1)


if __name__ == "__main__":
    unittest.main()
