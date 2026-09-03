from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services.query_planner import deterministic_plan, plan_search


class QueryPlannerTests(unittest.TestCase):
    now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)

    def test_relative_dates_use_configured_timezone_and_utc_boundaries(self):
        with patch.object(settings, "APP_TIMEZONE", "Asia/Karachi"):
            plan = deterministic_plan(
                "Show PDF files created yesterday", limit=10, now=self.now
            )
        self.assertEqual(plan.intent, "file_discovery")
        self.assertEqual(plan.date_field, "created_time")
        self.assertEqual(plan.start, datetime(2026, 8, 29, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(plan.end, datetime(2026, 8, 30, 18, 59, 59, 999999, tzinfo=timezone.utc))

    def test_modified_this_week(self):
        plan = deterministic_plan("Show files modified this week", limit=10, now=self.now)
        self.assertEqual(plan.date_field, "modified_time")
        self.assertEqual(plan.start, datetime(2026, 8, 30, 19, 0, tzinfo=timezone.utc))

    def test_explicit_august_range_is_inclusive(self):
        plan = deterministic_plan(
            "Give me project files from August 1 to August 5, 2026", limit=10, now=self.now
        )
        self.assertEqual(plan.start, datetime(2026, 7, 31, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(plan.end, datetime(2026, 8, 5, 18, 59, 59, 999999, tzinfo=timezone.utc))

    def test_content_and_structured_intents(self):
        self.assertEqual(deterministic_plan("Does Umer have Django experience?", limit=8).intent, "content_question")
        self.assertEqual(deterministic_plan("Find documents about AI automation", limit=8).intent, "content_search")
        self.assertEqual(deterministic_plan("How many PDF files do I have?", limit=8).intent, "aggregate")
        self.assertEqual(deterministic_plan("Show my folders", limit=8).intent, "file_discovery")

    def test_person_roles_are_not_conflated(self):
        self.assertEqual(deterministic_plan("Show files owned by Ali", limit=8).person_role, "owner")
        self.assertEqual(deterministic_plan("Give me files sent by Ali yesterday", limit=8).person_role, "sender")
        self.assertEqual(deterministic_plan("Show files modified by Ali", limit=8).person_role, "last_modifier")
        self.assertEqual(deterministic_plan("What changes did Ali perform yesterday?", limit=8).person_role, "activity_actor")

    def test_invalid_gemini_plan_is_rejected(self):
        response = SimpleNamespace(parsed={"intent": "file_discovery", "sql": "unsafe", "limit": 500})
        client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_kwargs: response))
        with (
            patch("app.services.query_planner.deterministic_plan", return_value=None),
            patch("app.services.query_planner.get_gemini_client", return_value=client),
            patch.object(settings, "GEMINI_API_KEY", "test-key"),
            patch.object(settings, "GEMINI_CHAT_MODEL", "test-model"),
        ):
            plan = plan_search("ambiguous long request requiring a proposed structured interpretation", limit=8)
        self.assertEqual(plan.intent, "content_question")
        self.assertFalse(hasattr(plan, "sql"))

    def test_gemini_outage_falls_back_safely(self):
        with (
            patch("app.services.query_planner.deterministic_plan", return_value=None),
            patch("app.services.query_planner._gemini_plan", side_effect=RuntimeError("provider detail")),
        ):
            plan = plan_search("ambiguous long request requiring safe fallback behavior", limit=8)
        self.assertEqual(plan.intent, "content_question")


if __name__ == "__main__":
    unittest.main()
