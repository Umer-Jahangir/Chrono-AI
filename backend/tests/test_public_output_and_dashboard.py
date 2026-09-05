import uuid
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import engine, get_db
from app.db.models import GoogleDriveEvent, Memory, MemoryChunk
from app.main import app
from app.services.ai_provider import AIProviderNotConfigured
from app.services.auth import get_current_user
from app.services.output_safety import redact_public_text, safe_drive_open_url


class PublicOutputAndDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = engine.connect()
        cls.transaction = cls.connection.begin()
        cls.db = Session(bind=cls.connection, join_transaction_mode="create_savepoint")
        cls.user_id = f"public-output-{uuid.uuid4().hex}"
        cls.other_user_id = f"public-output-other-{uuid.uuid4().hex}"
        cls.active_user_id = cls.user_id
        cls.file_id = f"safe-file-{uuid.uuid4().hex}"
        cls.safe_url = "https://drive.google.com/file/d/safe-fixture/view"
        cls.memory = cls._memory(
            cls.user_id, cls.file_id, "Safe Drive Fixture.pdf", cls.safe_url,
            "safelinktoken Contact owner@example.invalid or +1 (202) 555-0198.",
        )
        cls.db.add(MemoryChunk(
            memory_id=cls.memory.id, chunk_index=0, content=cls.memory.content,
            token_count=8, metadata_json={"mime_type": "application/pdf"},
        ))
        cls.db.add(MemoryChunk(
            memory_id=cls.memory.id, chunk_index=1,
            content="A second safelinktoken evidence passage for grouped citations.",
            token_count=8, metadata_json={"mime_type": "application/pdf"},
        ))
        for index, (title, url) in enumerate((
            ("Docs URL.pdf", "https://docs.google.com/document/d/safe/edit"),
            ("HTTP URL.pdf", "http://drive.google.com/file/d/no/view"),
            ("Script URL.pdf", "javascript:alert(1)"),
            ("Data URL.pdf", "data:text/html,hello"),
            ("Credential URL.pdf", "https://user:pass@drive.google.com/file/d/no/view"),
            ("Lookalike URL.pdf", "https://drive.google.com.attacker.example/file/d/no/view"),
            ("Evil URL.pdf", "https://evil-drive.google.com/file/d/no/view"),
            ("Missing URL.pdf", None),
        )):
            cls._memory(cls.user_id, f"url-{index}-{uuid.uuid4().hex}", title, url, "")
        cls._memory(
            cls.other_user_id, f"other-{uuid.uuid4().hex}", "Other User Private Link.pdf",
            "https://drive.google.com/file/d/private/view", "otherprivateurltoken",
        )
        for suffix, event_type, occurred_at in (
            ("before", "created", datetime(2026, 8, 30, 18, 59, tzinfo=timezone.utc)),
            ("boundary", "created", datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc)),
            ("inside", "modified", datetime(2026, 8, 30, 19, 30, tzinfo=timezone.utc)),
            ("future", "deleted", datetime(2026, 8, 30, 20, 1, tzinfo=timezone.utc)),
        ):
            cls.db.add(GoogleDriveEvent(
                user_id=cls.user_id, drive_id="dashboard-test",
                change_id=f"{suffix}-{uuid.uuid4().hex}", event_type=event_type,
                file_id=cls.file_id, name="Safe Drive Fixture.pdf",
                mime_type="application/pdf", is_folder=False,
                removed=event_type == "deleted", occurred_at=occurred_at,
                payload={"webViewLink": cls.safe_url},
            ))
        cls.db.add(GoogleDriveEvent(
            user_id=cls.other_user_id, drive_id="dashboard-other",
            change_id=f"other-{uuid.uuid4().hex}", event_type="moved",
            file_id="other-private", name="Other User Event", mime_type="text/plain",
            is_folder=False, removed=False,
            occurred_at=datetime(2026, 8, 30, 19, 10, tzinfo=timezone.utc), payload={},
        ))
        cls.db.flush()

        def override_db():
            yield cls.db

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=cls.active_user_id)
        cls.client = TestClient(app)

    @classmethod
    def _memory(cls, user_id, source_id, title, url, content):
        memory = Memory(
            user_id=user_id, source="google_drive", source_id=source_id,
            title=title, content=content, event_type="modified",
            event_date=datetime(2026, 8, 30, 19, 30, tzinfo=timezone.utc),
            file_url=url,
            metadata_json={
                "name": title, "mime_type": "application/pdf",
                "raw_change": {"file": {"webViewLink": url}} if url else {"file": {}},
            },
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

    def setUp(self):
        self.__class__.active_user_id = self.user_id

    def test_safe_drive_url_allowlist(self):
        self.assertEqual(safe_drive_open_url(self.safe_url), self.safe_url)
        docs_url = "https://docs.google.com/document/d/fixture/edit"
        self.assertEqual(safe_drive_open_url(docs_url), docs_url)
        for unsafe in (
            "http://drive.google.com/file/d/no/view", "javascript:alert(1)",
            "data:text/html,hello", "https://user:pass@drive.google.com/file/d/no/view",
            "https://drive.google.com.attacker.example/file/d/no/view",
            "https://evil-drive.google.com/file/d/no/view",
            "https://drive.google.com:444/file/d/no/view", "not a url", None,
        ):
            with self.subTest(url=unsafe):
                self.assertIsNone(safe_drive_open_url(unsafe))

    def test_file_discovery_exposes_only_validated_links(self):
        response = self.client.post("/ask", json={"question": "Show my PDF files", "limit": 20})
        self.assertEqual(response.status_code, 200)
        items = {item["title"]: item for item in response.json()["items"]}
        self.assertEqual(items["Safe Drive Fixture.pdf"]["open_url"], self.safe_url)
        self.assertEqual(items["Docs URL.pdf"]["open_url"], "https://docs.google.com/document/d/safe/edit")
        for title in (
            "HTTP URL.pdf", "Script URL.pdf", "Data URL.pdf", "Credential URL.pdf",
            "Lookalike URL.pdf", "Evil URL.pdf", "Missing URL.pdf",
        ):
            self.assertIsNone(items[title]["open_url"])
        self.assertNotIn("Other User Private Link.pdf", items)

    def test_rag_sources_keep_only_cited_passages_redact_and_preserve_storage(self):
        original = self.memory.content
        with (
            patch("app.services.retrieval.create_embedding_batch", side_effect=AIProviderNotConfigured("disabled")),
            patch(
                "app.api.ask.answer_with_context",
                return_value="### Contact\n**Email:** owner@example.invalid\nPhone +1 202-555-0198 [1]",
            ),
        ):
            response = self.client.post("/ask", json={"question": "What is safelinktoken?"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["sources"][0]["open_url"], self.safe_url)
        self.assertEqual(len(body["sources"]), 1)
        self.assertEqual(len(body["sources"][0]["passages"]), 1)
        serialized = str(body)
        self.assertNotIn("owner@example.invalid", serialized)
        self.assertNotIn("555-0198", serialized)
        self.db.refresh(self.memory)
        self.assertEqual(self.memory.content, original)

    def test_timeline_and_history_are_sanitized_and_user_isolated(self):
        current = self.client.get("/timeline", params={"limit": 20}).json()
        history = self.client.get("/timeline/history", params={"limit": 20}).json()
        self.assertTrue(current["items"])
        self.assertTrue(history["items"])
        self.assertTrue(any(item["open_url"] == self.safe_url for item in current["items"]))
        self.assertTrue(all(item["open_url"] == self.safe_url for item in history["items"]))
        for payload in (current, history):
            serialized = str(payload)
            self.assertNotIn("metadata", serialized)
            self.assertNotIn("file_id", serialized)
            self.assertNotIn("user_id", serialized)
            self.assertNotIn("owner@example.invalid", serialized)

    def test_unauthenticated_dashboard_is_rejected(self):
        override = app.dependency_overrides.pop(get_current_user)
        try:
            self.assertEqual(self.client.get("/dashboard/summary").status_code, 401)
        finally:
            app.dependency_overrides[get_current_user] = override

    def test_dashboard_aggregation_timezone_counts_and_isolation(self):
        fixed_now = datetime(2026, 8, 31, 1, 0, tzinfo=ZoneInfo("Asia/Karachi"))
        with patch("app.api.dashboard._local_now", return_value=fixed_now):
            response = self.client.get("/dashboard/summary", params={"range": "this_week"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["timezone"], "Asia/Karachi")
        self.assertEqual(body["event_count"], 2)
        self.assertEqual(body["event_counts"]["created"], 1)
        self.assertEqual(body["event_counts"]["modified"], 1)
        self.assertEqual(body["event_counts"]["moved"], 0)
        self.assertEqual(body["days"], [{
            "date": "2026-08-31", "total": 2, "created": 1, "modified": 1,
            "moved": 0, "trashed": 0, "restored": 0, "deleted": 0,
        }])
        self.assertTrue(body["recent_items"])
        self.assertNotIn("Other User Event", str(body))

    def test_dashboard_empty_state_and_allowlisted_ranges(self):
        self.__class__.active_user_id = f"empty-{uuid.uuid4().hex}"
        fixed_now = datetime(2026, 8, 31, 1, 0, tzinfo=ZoneInfo("Asia/Karachi"))
        with patch("app.api.dashboard._local_now", return_value=fixed_now):
            body = self.client.get("/dashboard/summary", params={"range": "last_7_days"}).json()
        self.assertEqual(body["event_count"], 0)
        self.assertEqual(body["recent_items"], [])
        self.assertEqual(len(body["days"]), 7)
        self.assertTrue(all(day["total"] == 0 for day in body["days"]))
        self.assertEqual(
            self.client.get("/dashboard/summary", params={"range": "all_time"}).status_code,
            422,
        )

    def test_redaction_handles_contact_details_and_secrets(self):
        value = redact_public_text(
            "Email me@example.com, call +44 20 7946 0958, token sk-abcdefghijklmnop. Date 2026-08-29."
        )
        self.assertNotIn("me@example.com", value)
        self.assertNotIn("7946 0958", value)
        self.assertNotIn("sk-abcdefghijklmnop", value)
        self.assertIn("2026-08-29", value)


if __name__ == "__main__":
    unittest.main()
