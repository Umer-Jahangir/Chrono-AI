import json
import uuid
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import engine, get_db
from app.db.models import GoogleDriveEvent, Memory, MemoryChunk, User
from app.main import app
from app.services.ai_provider import AIProviderNotConfigured
from app.services.auth import (
    AuthenticationError,
    GoogleIdentity,
    issue_access_token,
    verify_google_identity,
)
from app.services.ownership_claim import OwnershipClaimError, claim_default_user_data


def _identity(subject: str, email: str = "owner@example.invalid") -> GoogleIdentity:
    return GoogleIdentity(
        subject=subject,
        email=email,
        email_verified=True,
        display_name="Fixture User",
        picture_url=None,
    )


class AuthAndOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = engine.connect()
        cls.transaction = cls.connection.begin()
        cls.db = Session(bind=cls.connection, join_transaction_mode="create_savepoint")
        cls.secret_patch = patch.object(settings, "CHRONO_JWT_SECRET", "test-only-secret-at-least-32-characters")
        cls.client_patch = patch.object(settings, "GOOGLE_AUTH_CLIENT_ID", "test-client.apps.googleusercontent.com")
        cls.n8n_secret_patch = patch.object(settings, "N8N_WEBHOOK_SECRET", "test-n8n-secret")
        cls.legacy_patch = patch.object(settings, "ALLOW_LEGACY_DEFAULT_USER", False)
        for active_patch in (cls.secret_patch, cls.client_patch, cls.n8n_secret_patch, cls.legacy_patch):
            active_patch.start()

        def override_db():
            yield cls.db

        app.dependency_overrides[get_db] = override_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        app.dependency_overrides.clear()
        cls.client.close()
        for active_patch in (cls.legacy_patch, cls.n8n_secret_patch, cls.client_patch, cls.secret_patch):
            active_patch.stop()
        cls.db.close()
        cls.transaction.rollback()
        cls.connection.close()
        engine.dispose()

    def _new_user(self, *, email: str | None = None, active: bool = True) -> User:
        suffix = uuid.uuid4().hex
        user = User(
            google_subject=f"google-{suffix}",
            email=email or f"{suffix}@example.invalid",
            email_verified=True,
            display_name="Fixture User",
            is_active=active,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def _headers(self, user: User, *, now: datetime | None = None) -> dict[str, str]:
        token, _ = issue_access_token(user, now=now)
        return {"Authorization": f"Bearer {token}"}

    def _memory(self, user: User, token: str, title: str) -> Memory:
        memory = Memory(
            user_id=str(user.id),
            source="auth-fixture",
            source_id=f"source-{uuid.uuid4().hex}",
            title=title,
            content=f"{token} private evidence",
            event_type="created",
            event_date=datetime.now(timezone.utc),
            metadata_json={"mime_type": "text/plain"},
        )
        self.db.add(memory)
        self.db.flush()
        return memory

    def test_google_login_creates_reuses_and_tracks_sub_when_email_changes(self):
        subject = f"login-{uuid.uuid4().hex}"
        with patch("app.api.auth.verify_google_identity", return_value=_identity(subject)):
            first = self.client.post("/auth/google", json={"credential": "mock-google-token"})
            second = self.client.post("/auth/google", json={"credential": "mock-google-token"})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["user"]["id"], second.json()["user"]["id"])
        self.assertEqual(first.json()["token_type"], "bearer")
        self.assertGreater(first.json()["expires_in"], 0)
        self.assertNotIn("google_subject", first.json()["user"])
        self.assertNotIn("mock-google-token", json.dumps(first.json()))

        with patch(
            "app.api.auth.verify_google_identity",
            return_value=_identity(subject, "changed@example.invalid"),
        ):
            changed = self.client.post("/auth/google", json={"credential": "mock-google-token"})
        self.assertEqual(changed.json()["user"]["id"], first.json()["user"]["id"])
        self.assertEqual(changed.json()["user"]["email"], "changed@example.invalid")
        self.assertEqual(self.db.query(User).filter(User.google_subject == subject).count(), 1)

    def test_google_verification_rejects_invalid_claims(self):
        valid = {
            "iss": "https://accounts.google.com",
            "aud": settings.GOOGLE_AUTH_CLIENT_ID,
            "sub": "stable-sub",
            "email": "verified@example.invalid",
            "email_verified": True,
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        }
        with patch("app.services.auth.google_id_token.verify_oauth2_token", return_value=valid):
            self.assertEqual(verify_google_identity("mock").subject, "stable-sub")
        for claims in (
            {**valid, "aud": "wrong-client"},
            {**valid, "iss": "https://issuer.invalid"},
            {key: value for key, value in valid.items() if key != "sub"},
            {**valid, "email_verified": False},
            {**valid, "exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())},
        ):
            with (
                self.subTest(claims=sorted(claims)),
                patch("app.services.auth.google_id_token.verify_oauth2_token", return_value=claims),
            ):
                with self.assertRaises(AuthenticationError):
                    verify_google_identity("mock")
        for provider_error in (ValueError("invalid signature"), ValueError("expired")):
            with patch(
                "app.services.auth.google_id_token.verify_oauth2_token",
                side_effect=provider_error,
            ):
                with self.assertRaises(AuthenticationError):
                    verify_google_identity("mock")

    def test_me_and_bearer_failure_modes(self):
        user = self._new_user()
        good = self.client.get("/auth/me", headers=self._headers(user))
        self.assertEqual(good.status_code, 200)
        self.assertEqual(good.json()["id"], str(user.id))
        self.assertNotIn("google_subject", good.json())
        self.assertEqual(self.client.get("/auth/me").status_code, 401)
        self.assertEqual(
            self.client.get("/auth/me", headers={"Authorization": "Bearer invalid"}).status_code,
            401,
        )
        expired_headers = self._headers(
            user,
            now=datetime.now(timezone.utc) - timedelta(minutes=settings.CHRONO_ACCESS_TOKEN_MINUTES + 1),
        )
        self.assertEqual(self.client.get("/auth/me", headers=expired_headers).status_code, 401)
        user.is_active = False
        self.db.flush()
        self.assertEqual(self.client.get("/auth/me", headers=self._headers(user)).status_code, 401)
        user.is_active = True
        self.db.flush()
        deleted = self._new_user()
        deleted_headers = self._headers(deleted)
        self.db.delete(deleted)
        self.db.flush()
        self.assertEqual(self.client.get("/auth/me", headers=deleted_headers).status_code, 401)

    def test_protected_endpoints_derive_owner_and_ignore_client_user_id(self):
        user_a = self._new_user()
        user_b = self._new_user()
        self._memory(user_a, "alphauniquetoken", "Alpha Record")
        self._memory(user_b, "betauniquetoken", "Beta Record")
        self.db.add_all([
            GoogleDriveEvent(
                user_id=str(user_a.id), drive_id="drive-a", change_id=f"a-{uuid.uuid4().hex}",
                event_type="created", file_id="file-a", name="Alpha Event", mime_type="text/plain",
                is_folder=False, removed=False, occurred_at=datetime.now(timezone.utc), payload={},
            ),
            GoogleDriveEvent(
                user_id=str(user_b.id), drive_id="drive-b", change_id=f"b-{uuid.uuid4().hex}",
                event_type="created", file_id="file-b", name="Beta Event", mime_type="text/plain",
                is_folder=False, removed=False, occurred_at=datetime.now(timezone.utc), payload={},
            ),
        ])
        self.db.flush()
        headers = self._headers(user_a)
        search = self.client.get(
            "/search",
            params={"q": "betauniquetoken", "user_id": str(user_b.id)},
            headers=headers,
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["count"], 0)
        memories = self.client.get("/memories", headers=headers).json()
        self.assertTrue(memories)
        self.assertTrue(all(row["title"] == "Alpha Record" for row in memories))
        self.assertTrue(all("user_id" not in row and "metadata_json" not in row for row in memories))
        timeline = self.client.get("/timeline", params={"user_id": str(user_b.id)}, headers=headers).json()
        self.assertTrue(timeline["items"])
        self.assertTrue(all(row["title"] == "Alpha Record" for row in timeline["items"]))
        self.assertTrue(all("user_id" not in row for row in timeline["items"]))
        history = self.client.get("/timeline/history", headers=headers).json()
        self.assertEqual([row["title"] for row in history["items"]], ["Alpha Event"])
        with (
            patch(
                "app.services.retrieval.create_embedding_batch",
                side_effect=AIProviderNotConfigured("disabled"),
            ),
            patch(
                "app.api.ask.answer_with_context",
                side_effect=AIProviderNotConfigured("disabled"),
            ),
        ):
            # The supplied user_id is ignored; authenticated ownership wins.
            asked = self.client.post(
                "/ask",
                json={
                    "question": "Find document mentioning alphauniquetoken",
                    "user_id": str(user_b.id),
                },
                headers=headers,
            )
        self.assertEqual(asked.status_code, 200)
        self.assertNotIn("Beta Record", json.dumps(asked.json()))
        self.assertEqual(self.client.post("/ask", json={"question": "Show my files"}).status_code, 401)
        self.assertEqual(self.client.get("/integrations/google-drive/status").status_code, 401)
        self.assertEqual(self.client.get("/integrations/google-drive/events").status_code, 401)

    def test_n8n_owner_is_server_mapped_and_payload_user_is_ignored(self):
        owner = self._new_user()
        attacker = self._new_user()
        event = {
            "source": "google_drive",
            "drive_id": "mapped-drive",
            "change_id": f"mapped-{uuid.uuid4().hex}",
            "event_type": "created",
            "file_id": f"mapped-file-{uuid.uuid4().hex}",
            "name": "Mapped Fixture",
            "mime_type": "application/vnd.google-apps.folder",
            "is_folder": True,
            "removed": False,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "parents": [],
            "previous_parents": [],
            "owners": [],
            "raw_change": {},
            "user_id": str(attacker.id),
        }
        with patch.object(settings, "CHRONO_N8N_OWNER_USER_ID", str(owner.id)):
            invalid = self.client.post(
                "/integrations/google-drive/events", json=event,
                headers={"X-N8N-Secret": "wrong"},
            )
            accepted = self.client.post(
                "/integrations/google-drive/events", json=event,
                headers={"X-N8N-Secret": settings.N8N_WEBHOOK_SECRET},
            )
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        row = self.db.query(GoogleDriveEvent).filter_by(change_id=event["change_id"]).one()
        memory = self.db.query(Memory).filter_by(source_id=event["file_id"]).one()
        self.assertEqual(row.user_id, str(owner.id))
        self.assertEqual(memory.user_id, str(owner.id))
        self.assertNotIn("user_id", row.payload)

    def test_claim_dry_run_apply_preserves_ids_vectors_and_is_idempotent(self):
        # Hide pre-existing legacy rows inside the outer rollback transaction so
        # this test's migration counts and writes are fixture-only.
        sentinel = f"preexisting-{uuid.uuid4().hex}"
        self.db.query(Memory).filter(Memory.user_id == "default").update(
            {Memory.user_id: sentinel}, synchronize_session=False
        )
        self.db.query(GoogleDriveEvent).filter(
            or_(GoogleDriveEvent.user_id == "default", GoogleDriveEvent.user_id.is_(None))
        ).update({GoogleDriveEvent.user_id: sentinel}, synchronize_session=False)
        self.db.flush()
        target = self._new_user(email=f"claim-{uuid.uuid4().hex}@example.invalid")
        memory = Memory(
            user_id="default", source="google_drive", source_id=f"claim-{uuid.uuid4().hex}",
            title="Claim Fixture", content="preserved content", event_type="created",
            event_date=datetime.now(timezone.utc), metadata_json={},
        )
        self.db.add(memory)
        self.db.flush()
        chunk = MemoryChunk(
            memory_id=memory.id, chunk_index=0, content="preserved chunk", token_count=2,
            embedding=[1.0] + [0.0] * 1535, embedding_provider="fake",
            embedding_model="fake-v1", embedding_dimensions=1536,
        )
        event = GoogleDriveEvent(
            user_id=None, drive_id="legacy", change_id=f"claim-{uuid.uuid4().hex}",
            event_type="created", file_id=memory.source_id, name=memory.title,
            mime_type="text/plain", is_folder=False, removed=False,
            occurred_at=memory.event_date, payload={},
        )
        self.db.add_all([chunk, event])
        self.db.flush()
        ids = (memory.id, chunk.id, event.id)

        dry = claim_default_user_data(self.db, email=target.email.upper(), apply=False)
        self.assertEqual(dry.before.memories, 1)
        self.assertEqual(dry.before.drive_events, 1)
        self.assertEqual(dry.updated.memories, 0)
        self.assertEqual(memory.user_id, "default")

        applied = claim_default_user_data(self.db, email=target.email, apply=True)
        self.db.expire_all()
        claimed_memory = self.db.get(Memory, ids[0])
        claimed_chunk = self.db.get(MemoryChunk, ids[1])
        claimed_event = self.db.get(GoogleDriveEvent, ids[2])
        self.assertEqual(applied.updated.memories, 1)
        self.assertEqual(applied.updated.drive_events, 1)
        self.assertEqual(applied.after.memories, 0)
        self.assertEqual(claimed_memory.user_id, str(target.id))
        self.assertEqual(claimed_chunk.memory_id, claimed_memory.id)
        self.assertIsNotNone(claimed_chunk.embedding)
        self.assertEqual(claimed_event.user_id, str(target.id))
        again = claim_default_user_data(self.db, email=target.email, apply=True)
        self.assertEqual(again.updated.memories, 0)
        self.assertEqual(again.updated.drive_events, 0)

    def test_claim_rolls_back_all_updates_on_failure_and_refuses_ambiguity(self):
        target = self._new_user(email=f"rollback-{uuid.uuid4().hex}@example.invalid")
        legacy = Memory(
            user_id="default", source="rollback", source_id=f"rollback-{uuid.uuid4().hex}",
            title="Rollback Fixture", content="safe", event_type="created",
            event_date=datetime.now(timezone.utc), metadata_json={},
        )
        self.db.add(legacy)
        self.db.flush()
        with self.assertRaises(RuntimeError):
            claim_default_user_data(
                self.db, email=target.email, apply=True,
                before_commit=lambda: (_ for _ in ()).throw(RuntimeError("fixture failure")),
            )
        self.db.expire_all()
        self.assertEqual(self.db.get(Memory, legacy.id).user_id, "default")
        with self.assertRaises(OwnershipClaimError):
            claim_default_user_data(self.db, email="missing@example.invalid", apply=False)
        ambiguous_email = f"ambiguous-{uuid.uuid4().hex}@example.invalid"
        self._new_user(email=ambiguous_email)
        self._new_user(email=ambiguous_email.upper())
        with self.assertRaises(OwnershipClaimError):
            claim_default_user_data(self.db, email=ambiguous_email, apply=False)


if __name__ == "__main__":
    unittest.main()
