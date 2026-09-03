import json
import uuid
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import engine, get_db
from app.db.models import GoogleDriveEvent, Memory, MemoryChunk
from app.main import app
from app.services.auth import get_current_user
from app.services.ai_provider import EmbeddingBatch, EmbeddingSpec


def vector(axis: int = 0) -> list[float]:
    values = [0.0] * 1536
    values[axis] = 1.0
    return values


class SchemaAwareAskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.now_patcher = patch(
            "app.services.query_planner._local_now",
            return_value=datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc),
        )
        cls.now_patcher.start()
        cls.connection = engine.connect()
        cls.transaction = cls.connection.begin()
        cls.db = Session(bind=cls.connection, join_transaction_mode="create_savepoint")
        cls.suffix = uuid.uuid4().hex
        cls.user = f"schema-user-{cls.suffix}"
        cls.other_user = f"schema-other-{cls.suffix}"
        cls.source = "google_drive"

        owner = {"displayName": "Umer Jahangir", "emailAddress": "umer.fixture@example.invalid"}
        cls.resume = cls._memory(
            "Umer_Jahangir_Resume_AI.pdf",
            "Umer Jahangir has Python, Django, computer vision, and AI automation skills. "
            "His professional experience includes backend engineering and machine-learning systems.",
            "application/pdf", "2026-08-29T10:00:00Z", "2026-08-31T06:00:00Z", [owner],
        )
        cls.yesterday_pdf = cls._memory(
            "Metadata_Only_Yesterday.pdf", "", "application/pdf",
            "2026-08-30T06:00:00Z", "2026-08-30T07:00:00Z", [owner],
        )
        cls.range_pdf = cls._memory(
            "August_Project.pdf", "", "application/pdf",
            "2026-08-03T08:00:00Z", "2026-08-04T08:00:00Z", [owner],
        )
        cls.folder = cls._memory(
            "Chrono Projects", "", "application/vnd.google-apps.folder",
            "2026-08-30T08:00:00Z", "2026-08-31T08:00:00Z", [owner], is_folder=True,
        )
        cls.trashed = cls._memory(
            "Old Notes.txt", "", "text/plain",
            "2026-08-01T08:00:00Z", "2026-08-30T08:00:00Z", [owner],
            event_type="trashed", trashed=True,
        )
        cls.other = cls._memory(
            "Other User Secret.pdf", "private cross user content", "application/pdf",
            "2026-08-30T08:00:00Z", "2026-08-31T08:00:00Z", [owner], user_id=cls.other_user,
        )

        cls.db.flush()
        for index, content in enumerate([
            "Umer Jahangir has Python and Django technical skills.",
            "Professional experience includes computer vision and AI automation projects.",
        ]):
            cls.db.add(MemoryChunk(
                memory_id=cls.resume.id,
                chunk_index=index,
                content=content,
                token_count=12,
                metadata_json={"mime_type": "application/pdf"},
                embedding=vector(),
                embedding_provider="fake",
                embedding_model="schema-test",
                embedding_dimensions=1536,
            ))
        for index in range(3):
            cls.db.add(MemoryChunk(
                memory_id=cls.yesterday_pdf.id,
                chunk_index=index,
                content=f"duplicate count fixture passage {index}",
                token_count=6,
                metadata_json={"mime_type": "application/pdf"},
            ))

        cls.history_filename = f"History_{cls.suffix}.pdf"
        for event_type, occurred in (("created", "2026-08-29T20:00:00Z"), ("deleted", "2026-08-30T10:00:00Z")):
            cls.db.add(GoogleDriveEvent(
                user_id=cls.user,
                drive_id=f"test-drive-{cls.suffix}",
                change_id=f"{event_type}-{cls.suffix}",
                event_type=event_type,
                file_id=f"history-file-{cls.suffix}",
                name=cls.history_filename,
                mime_type="application/pdf",
                is_folder=False,
                removed=event_type == "deleted",
                occurred_at=datetime.fromisoformat(occurred.replace("Z", "+00:00")),
                payload={
                    "name": cls.history_filename,
                    "mime_type": "application/pdf",
                    "event_type": event_type,
                    "occurred_at": occurred,
                    "owners": [],
                    "raw_change": {"file": {"createdTime": "2026-08-29T20:00:00Z", "modifiedTime": occurred}},
                },
            ))
        cls.db.flush()

        def override_db():
            yield cls.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=cls.user)
        cls.client = TestClient(app)

    @classmethod
    def _memory(
        cls, title, content, mime_type, created, modified, owners,
        *, is_folder=False, event_type="modified", trashed=False, user_id=None,
    ):
        metadata = {
            "name": title,
            "mime_type": mime_type,
            "is_folder": is_folder,
            "owners": owners,
            "raw_change": {"file": {
                "name": title,
                "mimeType": mime_type,
                "createdTime": created,
                "modifiedTime": modified,
                "trashed": trashed,
                "owners": owners,
            }},
        }
        memory = Memory(
            user_id=user_id or cls.user,
            source=cls.source,
            source_id=f"{title}-{uuid.uuid4().hex}",
            title=title,
            content=content,
            event_type=event_type,
            event_date=datetime.fromisoformat(modified.replace("Z", "+00:00")),
            metadata_json=metadata,
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
        cls.now_patcher.stop()

    def fake_query_embedding(self, texts, **_kwargs):
        return EmbeddingBatch([vector() for _text in texts], EmbeddingSpec("fake", "schema-test", 1536))

    def ask(self, question, *, user_id=None, **payload):
        return self.client.post("/ask", json={
            "question": question,
            **({"user_id": user_id} if user_id is not None else {}),
            "limit": 10,
            **payload,
        })

    def test_resume_content_question_preserves_grounded_rag(self):
        with (
            patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_query_embedding),
            patch("app.api.ask.answer_with_context", return_value="Umer has Python and Django experience [1] and computer vision experience [2]."),
        ):
            response = self.ask("What technical skills and professional experience does Umer Jahangir have?")
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["intent"], "content_question")
        self.assertEqual(body["retrieval_mode"], "hybrid")
        self.assertEqual(body["sources"][0]["title"], "Umer_Jahangir_Resume_AI.pdf")
        self.assertIn("[1]", body["answer"])
        self.assertFalse({"memory_id", "chunk_id", "metadata"}.intersection(body))
        self.assertTrue({"answer", "retrieval_mode", "sources"}.issubset(body))

    def test_exact_and_semantic_content_search(self):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_query_embedding):
            exact = self.ask("Which document mentions computer vision?").json()
            semantic = self.ask("Find documents about visual machine perception").json()
        self.assertEqual(exact["intent"], "content_search")
        self.assertEqual(exact["items"][0]["title"], "Umer_Jahangir_Resume_AI.pdf")
        self.assertEqual(semantic["retrieval_mode"], "hybrid")
        self.assertEqual(semantic["items"][0]["title"], "Umer_Jahangir_Resume_AI.pdf")

    def test_created_modified_and_explicit_date_filters(self):
        created = self.ask("Show PDF files created yesterday").json()
        modified = self.ask("Show files modified this week").json()
        ranged = self.ask("Give me project files from August 1 to August 5, 2026").json()
        self.assertEqual(created["interpreted_filters"]["date_field"], "created_time")
        self.assertEqual([item["title"] for item in created["items"]], ["Metadata_Only_Yesterday.pdf"])
        self.assertEqual(modified["interpreted_filters"]["date_field"], "modified_time")
        self.assertIn("Umer_Jahangir_Resume_AI.pdf", [item["title"] for item in modified["items"]])
        self.assertIn("August_Project.pdf", [item["title"] for item in ranged["items"]])

    def test_folder_trashed_and_metadata_only_discovery(self):
        folders = self.ask("Show my folders").json()
        trashed = self.ask("Show trashed files").json()
        metadata_only = self.ask("Find Metadata_Only_Yesterday.pdf").json()
        self.assertEqual([item["title"] for item in folders["items"]], ["Chrono Projects"])
        self.assertEqual([item["title"] for item in trashed["items"]], ["Old Notes.txt"])
        self.assertEqual(metadata_only["items"][0]["title"], "Metadata_Only_Yesterday.pdf")
        self.assertEqual(self.db.query(MemoryChunk).filter_by(memory_id=self.folder.id).count(), 0)

    def test_current_timeline_deleted_history_and_partial_filename(self):
        current = self.ask("Show current Drive timeline").json()
        deleted = self.ask("Show deleted files", user_id="default").json()
        history = self.ask(f"Show the history of {self.history_filename}", user_id="default").json()
        self.assertEqual(current["intent"], "current_timeline")
        self.assertGreater(len(current["items"]), 0)
        self.assertIn(self.history_filename, [item["title"] for item in deleted["items"]])
        self.assertEqual([item["event_type"] for item in history["items"]], ["deleted", "created"])

    def test_pdf_count_counts_files_not_chunks(self):
        body = self.ask("How many PDF files do I have?").json()
        self.assertEqual(body["intent"], "aggregate")
        self.assertIn("3 files", body["answer"])
        self.assertEqual(body["items"], [])

    def test_owner_name_and_email_lookup_is_private(self):
        by_name = self.ask("Show files owned by Umer Jahangir").json()
        by_email_response = self.ask("Find files owned by umer.fixture@example.invalid")
        by_email = by_email_response.json()
        self.assertGreater(len(by_name["items"]), 0)
        self.assertGreater(len(by_email["items"]), 0)
        self.assertNotIn("umer.fixture@example.invalid", json.dumps(by_email))
        self.assertTrue(by_email["interpreted_filters"]["person_email_provided"])

    def test_duplicate_chunks_never_duplicate_structured_files(self):
        body = self.ask("Find Metadata_Only_Yesterday.pdf").json()
        self.assertEqual(len(body["items"]), 1)
        self.assertNotIn("date_from", body["interpreted_filters"])
        self.assertNotIn("date_to", body["interpreted_filters"])

    def test_missing_sharing_and_received_metadata_are_unsupported(self):
        shared = self.ask("Who shared this file with me?").json()
        received = self.ask("Show files received yesterday").json()
        sender = self.ask("Give me files sent by Ali yesterday").json()
        modifier = self.ask("Show files modified by Ali").json()
        actor = self.ask("What changes did Ali perform yesterday?").json()
        self.assertEqual(shared["intent"], "unsupported")
        self.assertIn("sharing-user", shared["answer"])
        self.assertEqual(received["intent"], "unsupported")
        self.assertIn("shared-with-me time", received["answer"])
        self.assertEqual(sender["intent"], "unsupported")
        self.assertIn("sender information", sender["answer"])
        self.assertEqual(modifier["intent"], "unsupported")
        self.assertIn("last-modifying-user", modifier["answer"])
        self.assertEqual(actor["intent"], "unsupported")
        self.assertIn("Drive Activity actor", actor["answer"])

    def test_user_isolation_for_every_intent(self):
        discovery = self.ask("Show my PDF files", user_id="no-such-user").json()
        aggregate = self.ask("How many PDF files do I have?", user_id="no-such-user").json()
        timeline = self.ask("Show current Drive timeline", user_id="no-such-user").json()
        history = self.ask(f"Show the history of {self.history_filename}", user_id="no-such-user").json()
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_query_embedding):
            content = self.ask("Which document mentions computer vision?", user_id="no-such-user").json()
        self.assertGreater(len(discovery["items"]), 0)
        self.assertIn("3 files", aggregate["answer"])
        self.assertGreater(len(timeline["items"]), 0)
        self.assertGreater(len(history["items"]), 0)
        self.assertGreater(len(content["items"]), 0)


if __name__ == "__main__":
    unittest.main()
