from datetime import datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import GoogleDriveEvent, User
from app.schemas.dashboard import DashboardDay, DashboardSummaryResponse
from app.services.auth import get_current_user
from app.api.timeline import current_memories_for_events, event_public_item


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
EVENT_TYPES = ("created", "modified", "moved", "trashed", "restored", "deleted")
RangeName = Literal["this_week", "last_7_days", "last_30_days"]


def _local_now() -> datetime:
    return datetime.now(ZoneInfo(settings.APP_TIMEZONE))


def _range_start(now: datetime, range_name: RangeName) -> datetime:
    if range_name == "this_week":
        first_date = now.date() - timedelta(days=now.weekday())
    elif range_name == "last_7_days":
        first_date = now.date() - timedelta(days=6)
    else:
        first_date = now.date() - timedelta(days=29)
    return datetime.combine(first_date, time.min, now.tzinfo)


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    range_name: RangeName = Query(default="this_week", alias="range"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardSummaryResponse:
    """Bounded immutable activity; Recent Memories means recent Drive events."""
    user_id = str(current_user.id)
    now = _local_now()
    local_start = _range_start(now, range_name)
    start_utc = local_start.astimezone(timezone.utc)
    end_utc = now.astimezone(timezone.utc)
    events = (
        db.query(GoogleDriveEvent)
        .filter(
            GoogleDriveEvent.user_id == user_id,
            GoogleDriveEvent.occurred_at >= start_utc,
            GoogleDriveEvent.occurred_at <= end_utc,
        )
        .order_by(GoogleDriveEvent.occurred_at.asc())
        .all()
    )
    day_values = {}
    cursor = local_start.date()
    while cursor <= now.date():
        day_values[cursor] = {event_type: 0 for event_type in EVENT_TYPES}
        cursor += timedelta(days=1)
    event_counts = {event_type: 0 for event_type in EVENT_TYPES}
    for event in events:
        if event.event_type not in event_counts:
            continue
        local_date = event.occurred_at.astimezone(now.tzinfo).date()
        if local_date in day_values:
            day_values[local_date][event.event_type] += 1
            event_counts[event.event_type] += 1
    days = [
        DashboardDay(date=day, total=sum(counts.values()), **counts)
        for day, counts in day_values.items()
    ]

    recent_events = (
        db.query(GoogleDriveEvent)
        .filter(GoogleDriveEvent.user_id == user_id)
        .order_by(GoogleDriveEvent.occurred_at.desc(), GoogleDriveEvent.received_at.desc())
        .limit(6)
        .all()
    )
    current = current_memories_for_events(db, user_id, recent_events)
    recent_items = [event_public_item(event, current.get(event.file_id)) for event in recent_events]
    return DashboardSummaryResponse(
        range=range_name,
        timezone=settings.APP_TIMEZONE,
        start=start_utc,
        end=end_utc,
        event_count=sum(event_counts.values()),
        event_counts=event_counts,
        days=days,
        recent_items=recent_items,
    )
