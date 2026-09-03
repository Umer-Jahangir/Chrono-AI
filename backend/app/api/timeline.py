from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import GoogleDriveEvent, Memory, User
from app.schemas.rag import StructuredItem, TimelineResponse
from app.services.auth import get_current_user
from app.services.metadata_normalizer import normalize_drive_event, normalize_memory
from app.services.output_safety import redact_public_text
from app.services.retrieval import make_excerpt


router = APIRouter(prefix="/timeline", tags=["Timeline"])


def memory_public_item(memory: Memory, *, max_excerpt_chars: int = 220) -> StructuredItem:
    metadata = normalize_memory(memory)
    excerpt = (
        redact_public_text(make_excerpt(memory.content, "", max_chars=max_excerpt_chars))
        if memory.content else None
    )
    return StructuredItem(
        title=metadata.title,
        source=metadata.source,
        mime_type=metadata.mime_type,
        item_type="folder" if metadata.is_folder else "file",
        event_type=metadata.event_type,
        event_date=metadata.event_date,
        created_time=metadata.created_time,
        modified_time=metadata.modified_time,
        owner_display_names=[person.display_name for person in metadata.owners if person.display_name],
        excerpt=excerpt,
        open_url=metadata.open_url,
    )


def event_public_item(event: GoogleDriveEvent, current_memory: Memory | None = None) -> StructuredItem:
    metadata = normalize_drive_event(event)
    current_metadata = normalize_memory(current_memory) if current_memory else None
    return StructuredItem(
        title=metadata.title,
        source="google_drive",
        mime_type=metadata.mime_type,
        item_type="folder" if metadata.is_folder else "file",
        event_type=metadata.event_type,
        event_date=metadata.event_date,
        owner_display_names=[person.display_name for person in metadata.owners if person.display_name],
        excerpt=(
            redact_public_text(make_excerpt(current_memory.content, "", max_chars=220))
            if current_memory and current_memory.content else None
        ),
        open_url=current_metadata.open_url if current_metadata else None,
    )


def current_memories_for_events(
    db: Session, user_id: str, events: list[GoogleDriveEvent]
) -> dict[str, Memory]:
    if not events:
        return {}
    return {
        memory.source_id: memory
        for memory in db.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.source == "google_drive",
            Memory.source_id.in_([event.file_id for event in events]),
        ).all()
    }


@router.get("", response_model=TimelineResponse)
def get_timeline(
    start: datetime | None = None,
    end: datetime | None = None,
    source: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelineResponse:
    query = db.query(Memory).filter(Memory.user_id == str(current_user.id))
    if start:
        query = query.filter(Memory.event_date >= start)
    if end:
        query = query.filter(Memory.event_date <= end)
    if source:
        query = query.filter(Memory.source == source)
    memories = query.order_by(Memory.event_date.desc()).limit(limit).all()
    return TimelineResponse(
        view="current", count=len(memories), items=[memory_public_item(row) for row in memories]
    )


@router.get("/history", response_model=TimelineResponse)
def get_timeline_history(
    start: datetime | None = None,
    end: datetime | None = None,
    event_type: str | None = None,
    file_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimelineResponse:
    user_id = str(current_user.id)
    query = db.query(GoogleDriveEvent).filter(GoogleDriveEvent.user_id == user_id)
    if start:
        query = query.filter(GoogleDriveEvent.occurred_at >= start)
    if end:
        query = query.filter(GoogleDriveEvent.occurred_at <= end)
    if event_type:
        query = query.filter(GoogleDriveEvent.event_type == event_type)
    if file_id:
        query = query.filter(GoogleDriveEvent.file_id == file_id)
    events = query.order_by(GoogleDriveEvent.occurred_at.desc()).offset(offset).limit(limit).all()
    current = current_memories_for_events(db, user_id, events)
    items = [event_public_item(event, current.get(event.file_id)) for event in events]
    return TimelineResponse(view="history", count=len(items), items=items)
