import json
import uuid
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.database import engine, get_db
from app.core.config import settings
from app.db.models import GoogleDriveEvent, Memory, MemoryChunk
from app.main import app
from app.api.ask import _finalize_citations
from app.services.auth import get_current_user
from app.services.ai_provider import AIProviderNotConfigured, EmbeddingBatch, EmbeddingSpec


def vector(axis: int = 0) -> list[float]:
    values = [0.0] * 1536
    values[axis] = 1.0
    return values


def cosine_vector(primary_axis: int, similarity: float, secondary_axis: int) -> list[float]:
    values = [0.0] * 1536
    values[primary_axis] = similarity
    values[secondary_axis] = (1.0 - similarity * similarity) ** 0.5
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
        cls.text_file = cls._memory(
            "fyp.txt", "This is a report file for my final year project.", "text/plain",
            "2026-08-28T08:00:00Z", "2026-08-29T08:00:00Z", [owner],
        )
        cls.research = cls._memory(
            "document.pdf", "Title of the Research Paper. The study evaluates digital archives.",
            "application/pdf", "2026-08-25T08:00:00Z", "2026-08-26T08:00:00Z", [owner],
        )
        cls.title_only = cls._memory(
            "QuantumLedger Notes.png", "", "image/png",
            "2026-08-27T08:00:00Z", "2026-08-28T08:00:00Z", [owner],
        )
        cls.case_csv = cls._memory(
            "Case.CSV", "", "Text/CSV; charset=utf-8",
            "2026-08-26T08:00:00Z", "2026-08-27T08:00:00Z", [owner],
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
        cls.db.add(MemoryChunk(
            memory_id=cls.text_file.id,
            chunk_index=0,
            content="This is a report file for my final year project.",
            token_count=8,
            metadata_json={"mime_type": "text/plain"},
            embedding=cosine_vector(1, 0.70, 2),
            embedding_provider="fake",
            embedding_model="schema-test",
            embedding_dimensions=1536,
        ))
        cls.db.add(MemoryChunk(
            memory_id=cls.research.id,
            chunk_index=0,
            content="Title of the Research Paper. The study evaluates digital archives.",
            token_count=10,
            metadata_json={"mime_type": "application/pdf"},
            embedding=vector(1),
            embedding_provider="fake",
            embedding_model="schema-test",
            embedding_dimensions=1536,
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
        vectors = []
        for text in texts:
            lowered = text.casefold()
            if "research" in lowered:
                vectors.append(vector(1))
            elif any(term in lowered for term in ("visual", "machine", "technical", "skills", "experience")):
                vectors.append(vector(0))
            else:
                vectors.append(vector(3))
        return EmbeddingBatch(vectors, EmbeddingSpec("fake", "schema-test", 1536))

    def ask(self, question, *, user_id=None, **payload):
        return self.client.post("/ask", json={
            "question": question,
            **({"user_id": user_id} if user_id is not None else {}),
            "limit": 10,
            **payload,
        })

    def citation_results(self):
        memories = [self.resume, self.resume, self.text_file, self.research]
        chunks = [
            self.db.query(MemoryChunk).filter_by(memory_id=memory.id).order_by(MemoryChunk.chunk_index).all()[
                1 if index == 1 else 0
            ]
            for index, memory in enumerate(memories)
        ]
        return [{
            "chunk_id": str(chunk.id), "memory_id": str(memory.id), "title": memory.title,
            "content": chunk.content, "event_date": memory.event_date,
        } for memory, chunk in zip(memories, chunks)]

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

    def test_exact_resume_question_falls_back_across_multiple_lexical_chunks(self):
        with (
            patch("app.services.retrieval.create_embedding_batch", side_effect=AIProviderNotConfigured("none")),
            patch("app.api.ask.answer_with_context", side_effect=AIProviderNotConfigured("none")),
        ):
            body = self.ask("What technical skills and experience does Umer Jahangir have?").json()
        self.assertEqual(body["retrieval_mode"], "lexical-extractive")
        self.assertEqual(body["sources"][0]["title"], "Umer_Jahangir_Resume_AI.pdf")
        self.assertGreaterEqual(len(body["sources"][0]["passages"]), 2)

    def test_generated_skills_answer_exposes_only_cited_resume_passages(self):
        with (
            patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_query_embedding),
            patch("app.api.ask.answer_with_context", return_value="Python and Django [1]; computer vision experience [2]."),
        ):
            body = self.ask("What technical skills and experience does Umer Jahangir have?").json()
        self.assertEqual([source["title"] for source in body["sources"]], ["Umer_Jahangir_Resume_AI.pdf"])
        self.assertEqual([passage["citation"] for passage in body["sources"][0]["passages"]], [1, 2])
        self.assertNotIn("fyp.txt", json.dumps(body))
        self.assertNotIn("document.pdf", json.dumps(body))

    def test_generated_answer_with_one_citation_returns_one_passage(self):
        with (
            patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_query_embedding),
            patch("app.api.ask.answer_with_context", return_value="Python and Django [1]."),
        ):
            body = self.ask("What technical skills and experience does Umer Jahangir have?").json()
        self.assertEqual(len(body["sources"]), 1)
        self.assertEqual([passage["citation"] for passage in body["sources"][0]["passages"]], [1])

    def test_citation_finalization_renumbers_deduplicates_and_drops_invalid(self):
        results = self.citation_results()
        answer, sources = _finalize_citations(
            self.db, answer="Evidence [1], [3], [4], and again [3].", results=results,
            question="evidence", user_id=self.user,
        )
        self.assertEqual(answer, "Evidence [1], [2], [3], and again [2].")
        self.assertEqual([source.citation for source in sources], [1, 2, 3])
        self.assertEqual([source.title for source in sources], [
            "Umer_Jahangir_Resume_AI.pdf", "fyp.txt", "document.pdf",
        ])
        invalid_answer, invalid_sources = _finalize_citations(
            self.db, answer="Unsupported marker [99].", results=results,
            question="evidence", user_id=self.user,
        )
        self.assertNotIn("[99]", invalid_answer)
        self.assertEqual(invalid_sources, [])

    def test_citation_finalization_keeps_genuinely_cited_multiple_documents(self):
        results = [self.citation_results()[0], self.citation_results()[3]]
        answer, sources = _finalize_citations(
            self.db, answer="Two supported facts [1] [2].", results=results,
            question="supported facts", user_id=self.user,
        )
        self.assertEqual(answer, "Two supported facts [1] [2].")
        self.assertEqual([source.title for source in sources], [
            "Umer_Jahangir_Resume_AI.pdf", "document.pdf",
        ])

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
        self.assertIn("4 files", body["answer"])
        self.assertEqual(body["items"], [])

    def test_text_discovery_and_count_enforce_plain_text_mime(self):
        for question in ("give me a text file", "give me text files only", "give me TXT files"):
            with self.subTest(question=question):
                body = self.ask(question).json()
                self.assertEqual(body["intent"], "file_discovery")
                self.assertEqual(body["interpreted_filters"]["mime_type"], "text/plain")
                self.assertEqual([item["title"] for item in body["items"]], ["fyp.txt"])
        count = self.ask("How many text files do I have?").json()
        self.assertEqual(count["answer"], "Chrono found 1 file.")

    def test_mime_variations_and_combined_owner_filter(self):
        csv_body = self.ask("give me CSV files").json()
        owned_pdfs = self.ask("Show PDF files owned by Umer Jahangir").json()
        self.assertEqual([item["title"] for item in csv_body["items"]], ["Case.CSV"])
        self.assertTrue(owned_pdfs["items"])
        self.assertTrue(all(item["mime_type"].casefold() == "application/pdf" for item in owned_pdfs["items"]))

    def test_topical_search_is_relevant_and_fails_closed(self):
        with patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_query_embedding):
            research = self.ask("find research related file").json()
            missing = self.ask("find unobtainiumquasar related file").json()
            typed = self.ask("find research related text file").json()
        self.assertEqual([item["title"] for item in research["items"]], ["document.pdf"])
        self.assertNotIn("Umer_Jahangir_Resume_AI.pdf", json.dumps(research))
        self.assertNotIn("fyp.txt", json.dumps(research))
        self.assertEqual(typed["items"], [])
        self.assertEqual(missing["items"], [])
        self.assertEqual(missing["answer"], "Chrono found no matching files.")

    def test_topical_search_can_match_title_without_a_chunk(self):
        body = self.ask("find quantumledger related file").json()
        self.assertEqual([item["title"] for item in body["items"]], ["QuantumLedger Notes.png"])

    def test_gemini_503_and_504_return_cited_extractive_fallback(self):
        for status_code in (503, 504):
            failure = RuntimeError("private provider detail")
            failure.status_code = status_code
            with self.subTest(status_code=status_code):
                with (
                    patch.object(settings, "GEMINI_API_KEY", "test-key"),
                    patch.object(settings, "GEMINI_CHAT_MODEL", "test-model"),
                    patch.object(settings, "OPENAI_API_KEY", ""),
                    patch("app.services.retrieval.create_embedding_batch", side_effect=self.fake_query_embedding),
                    patch("app.services.ai_provider._gemini_answer", side_effect=failure) as generate,
                    patch("app.services.ai_provider.time.sleep"),
                ):
                    body = self.ask("What technical skills and experience does Umer Jahangir have?").json()
                self.assertEqual(generate.call_count, 2)
                self.assertEqual(body["retrieval_mode"], "lexical-extractive")
                self.assertGreater(len(body["sources"]), 0)
                self.assertIn("[1]", body["answer"])

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
        self.assertIn("4 files", aggregate["answer"])
        self.assertGreater(len(timeline["items"]), 0)
        self.assertGreater(len(history["items"]), 0)
        self.assertGreater(len(content["items"]), 0)

    def test_authenticated_other_user_cannot_retrieve_primary_records(self):
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=self.other_user)
        try:
            body = self.ask("Show my PDF files", user_id=self.user).json()
        finally:
            app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=self.user)
        self.assertEqual([item["title"] for item in body["items"]], ["Other User Secret.pdf"])
        self.assertNotIn("Umer_Jahangir_Resume_AI.pdf", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
