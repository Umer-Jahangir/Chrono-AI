import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.schemas.rag import SearchPlan
from app.services.ai_provider import get_gemini_client


_MONTH_PATTERN = (
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+\d{1,2}(?:\s*,?\s*\d{4})?"
)
_ISO_PATTERN = r"\d{4}-\d{2}-\d{2}"
_DATE_PATTERN = rf"(?:{_MONTH_PATTERN}|{_ISO_PATTERN})"
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def _local_now(now: datetime | None = None) -> datetime:
    zone = ZoneInfo(settings.APP_TIMEZONE)
    if now is None:
        return datetime.now(zone)
    if now.tzinfo is None:
        return now.replace(tzinfo=zone)
    return now.astimezone(zone)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(settings.APP_TIMEZONE))
    return value.astimezone(timezone.utc)


def _utc_day_bounds(value: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(value, time.min, zone).astimezone(timezone.utc)
    end = datetime.combine(value, time.max, zone).astimezone(timezone.utc)
    return start, end


def _parse_date(value: str, default_year: int) -> date | None:
    cleaned = re.sub(r"\s+", " ", value.strip().replace(",", ""))
    for date_format in ("%Y-%m-%d", "%B %d %Y", "%B %d"):
        try:
            parsed = datetime.strptime(cleaned, date_format).date()
            return parsed.replace(year=default_year) if date_format == "%B %d" else parsed
        except ValueError:
            continue
    return None


def parse_date_range(question: str, *, now: datetime | None = None) -> tuple[datetime | None, datetime | None]:
    lowered = question.casefold()
    local_now = _local_now(now)
    zone = ZoneInfo(settings.APP_TIMEZONE)
    today = local_now.date()

    range_match = re.search(
        rf"(?:between|from)\s+({_DATE_PATTERN})\s+(?:and|to)\s+({_DATE_PATTERN})",
        lowered,
    )
    if range_match:
        second = _parse_date(range_match.group(2), today.year)
        first = _parse_date(range_match.group(1), second.year if second else today.year)
        if first and second:
            start, _ = _utc_day_bounds(min(first, second), zone)
            _, end = _utc_day_bounds(max(first, second), zone)
            return start, end

    on_match = re.search(rf"(?:\bon\s+)?({_DATE_PATTERN})", lowered)
    if on_match:
        parsed = _parse_date(on_match.group(1), today.year)
        if parsed:
            return _utc_day_bounds(parsed, zone)

    if re.search(r"\byesterday\b", lowered):
        return _utc_day_bounds(today - timedelta(days=1), zone)
    if re.search(r"\btoday\b", lowered):
        return _utc_day_bounds(today, zone)
    if "last week" in lowered:
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        start, _ = _utc_day_bounds(last_monday, zone)
        _, end = _utc_day_bounds(this_monday - timedelta(days=1), zone)
        return start, end
    if "this week" in lowered:
        monday = today - timedelta(days=today.weekday())
        start, _ = _utc_day_bounds(monday, zone)
        _, end = _utc_day_bounds(today, zone)
        return start, end
    if "this month" in lowered:
        start, _ = _utc_day_bounds(today.replace(day=1), zone)
        _, end = _utc_day_bounds(today, zone)
        return start, end
    return None, None


def _date_field(question: str) -> str | None:
    lowered = question.casefold()
    if any(term in lowered for term in ("received", "shared with me", "shared by", "sent by")):
        return "shared_with_me_time"
    if "created" in lowered:
        return "created_time"
    if "modified" in lowered:
        return "modified_time"
    if "indexed" in lowered or "imported" in lowered:
        return "created_at"
    if any(term in lowered for term in ("changed", "activity", "history", "deleted event")):
        return "occurred_at"
    return "event_date"


def _filename(question: str) -> str | None:
    without_emails = _EMAIL_PATTERN.sub("", question)
    matches = re.findall(r"[\w.-]+\.[A-Za-z0-9]{1,12}", without_emails)
    return matches[-1] if matches else None


def _person_filter(question: str) -> tuple[str | None, str | None, str | None]:
    lowered = question.casefold()
    role = None
    marker = None
    if "owned by" in lowered:
        role, marker = "owner", "owned by"
    elif "modified by" in lowered:
        role, marker = "last_modifier", "modified by"
    elif "sent by" in lowered:
        role, marker = "sender", "sent by"
    elif "shared by" in lowered or "who shared" in lowered:
        role, marker = "sharer", "shared by" if "shared by" in lowered else None
    elif "performed by" in lowered or ("changes did" in lowered and "perform" in lowered):
        role, marker = "activity_actor", "performed by" if "performed by" in lowered else None
    if role is None:
        return None, None, None
    email_match = _EMAIL_PATTERN.search(question)
    email = email_match.group(0) if email_match else None
    name = None
    if marker:
        start = lowered.find(marker) + len(marker)
        candidate = question[start:]
        candidate = re.split(
            r"\b(?:today|yesterday|this week|last week|this month|on|between|from)\b",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        candidate = candidate.strip(" ?.!,")
        if candidate and not _EMAIL_PATTERN.fullmatch(candidate):
            name = candidate
    return role, name, email


def deterministic_plan(
    question: str, *, limit: int, now: datetime | None = None
) -> SearchPlan | None:
    lowered = question.casefold().strip()
    start, end = parse_date_range(question, now=now)
    filename = _filename(question)
    role, person_name, person_email = _person_filter(question)

    mime_type = None
    if re.search(r"\bpdfs?\b", lowered):
        mime_type = "application/pdf"
    elif re.search(r"\bgoogle (?:docs?|documents?)\b", lowered):
        mime_type = "application/vnd.google-apps.document"

    item_type = "folder" if re.search(r"\bfolders?\b", lowered) else None
    if item_type is None and re.search(r"\bfiles?\b", lowered):
        item_type = "file"

    event_type = next(
        (value for value in ("deleted", "trashed", "restored", "moved", "modified", "created") if value in lowered),
        None,
    )
    trashed = True if "trashed" in lowered else None
    aggregate = "count" if re.search(r"\b(?:how many|count)\b", lowered) else None
    date_field = _date_field(question) if start or end else None
    title = "project" if "project files" in lowered else None

    base = {
        "query_text": question,
        "source": "google_drive" if any(
            term in lowered for term in ("drive", "file", "folder", "pdf", "owned", "shared", "sent")
        ) else None,
        "mime_type": mime_type,
        "item_type": item_type,
        "title": title,
        "filename": filename,
        "trashed": trashed,
        "person_name": person_name,
        "person_email": person_email,
        "person_role": role,
        "start": start,
        "end": end,
        "date_field": date_field,
        "limit": min(max(limit, 1), 50),
    }

    if aggregate:
        history_count = "event" in lowered or event_type in {"deleted", "restored", "moved"}
        return SearchPlan(
            intent="aggregate",
            aggregate="count",
            event_type=event_type if history_count else None,
            **base,
        )
    if "current timeline" in lowered or "current drive" in lowered:
        return SearchPlan(intent="current_timeline", event_type=None, **{k: v for k, v in base.items() if k != "event_type"})
    if role == "activity_actor" or "history" in lowered or "changed" in lowered or "drive activity" in lowered:
        return SearchPlan(intent="event_history", event_type=event_type, **base)
    if event_type == "deleted":
        return SearchPlan(intent="event_history", event_type="deleted", date_field=date_field or "occurred_at", **{k: v for k, v in base.items() if k != "date_field"})
    if "latest" in lowered and ("drive" in lowered or "activity" in lowered):
        return SearchPlan(intent="current_timeline", **base)
    if role or item_type or mime_type or filename or trashed is not None or (
        re.search(r"\b(?:show|find|give me)\b", lowered) and "document" not in lowered
    ):
        structured_event = event_type if event_type not in {"created", "modified"} else None
        return SearchPlan(intent="file_discovery", event_type=structured_event, **base)
    if any(phrase in lowered for phrase in ("which document", "find documents", "documents about", "mentions")):
        return SearchPlan(intent="content_search", **base)
    if lowered.endswith("?") or any(
        lowered.startswith(prefix) for prefix in ("what ", "does ", "do ", "summarize ", "explain ")
    ):
        return SearchPlan(intent="content_question", **base)
    if 1 <= len(lowered.split()) <= 8:
        return SearchPlan(intent="content_question", **base)
    return None


def _gemini_plan(question: str, *, limit: int, now: datetime | None = None) -> SearchPlan:
    if not settings.GEMINI_API_KEY or not settings.GEMINI_CHAT_MODEL:
        raise RuntimeError("Gemini planning is not configured")
    from google.genai import types

    local_now = _local_now(now)
    response = get_gemini_client().models.generate_content(
        model=settings.GEMINI_CHAT_MODEL,
        contents=(
            f"Classify this Chrono search request: {question}\n"
            f"Current local time: {local_now.isoformat()}. Timezone: {settings.APP_TIMEZONE}. "
            "Return a proposed plan only. Never produce SQL or database field names outside the schema. "
            "Use unsupported when the requested role cannot be represented by the schema."
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SearchPlan,
            temperature=0,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, SearchPlan):
        proposed = parsed.model_dump()
    elif isinstance(parsed, dict):
        proposed = parsed
    else:
        proposed = SearchPlan.model_validate_json(response.text).model_dump()
    proposed["limit"] = min(max(int(proposed.get("limit", limit)), 1), 50)
    plan = SearchPlan.model_validate(proposed)
    updates = {
        field_name: normalize_datetime(value)
        for field_name in ("start", "end")
        if (value := getattr(plan, field_name)) is not None
    }
    return plan.model_copy(update=updates) if updates else plan


def plan_search(question: str, *, limit: int, now: datetime | None = None) -> SearchPlan:
    deterministic = deterministic_plan(question, limit=limit, now=now)
    if deterministic is not None:
        return deterministic
    try:
        return _gemini_plan(question, limit=limit, now=now)
    except Exception:
        return SearchPlan(
            intent="content_question",
            query_text=question,
            limit=min(max(limit, 1), 50),
        )
