from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import GoogleDriveEvent, Memory
from app.schemas.rag import SearchPlan, StructuredItem
from app.services.metadata_normalizer import (
    NormalizedDriveMetadata,
    normalize_drive_event,
    normalize_memory,
    person_matches,
)
from app.services.file_types import normalize_mime_type


@dataclass(frozen=True)
class StructuredExecution:
    answer: str
    intent: str
    retrieval_mode: str
    interpreted_filters: dict
    items: list[StructuredItem]


def interpreted_filters(plan: SearchPlan) -> dict:
    result = {}
    for field_name in (
        "source", "event_type", "mime_type", "mime_types", "item_type", "title", "filename",
        "trashed", "person_name", "person_role", "date_field", "aggregate", "start", "end",
    ):
        value = getattr(plan, field_name)
        if value not in (None, []):
            result[field_name] = value.isoformat() if isinstance(value, datetime) else value
    if plan.person_email:
        result["person_email_provided"] = True
    return result


def _date_value(metadata: NormalizedDriveMetadata, field_name: str | None) -> datetime | None:
    selected = field_name or "event_date"
    return getattr(metadata, selected, None)


def _role_supported(rows: list[NormalizedDriveMetadata], plan: SearchPlan) -> tuple[bool, str | None]:
    if plan.person_role == "activity_actor":
        return False, (
            "Chrono cannot determine who performed Drive activity because Drive Activity actor "
            "information was not synchronized."
        )
    if plan.person_role == "sharer" and not any("sharing_user" in row.available_fields for row in rows):
        return False, (
            "Chrono cannot determine who shared this file because Google Drive sharing-user "
            "information was not synchronized."
        )
    if plan.person_role == "last_modifier" and not any(
        "last_modifying_user" in row.available_fields for row in rows
    ):
        return False, (
            "Chrono cannot determine who modified this file because Google Drive last-modifying-user "
            "information was not synchronized."
        )
    if plan.person_role == "sender" and plan.source in {None, "google_drive"}:
        return False, (
            "Chrono cannot determine who sent this Drive file because sender information is not "
            "part of the synchronized Google Drive metadata."
        )
    if plan.date_field == "shared_with_me_time" and not any(
        "shared_with_me_time" in row.available_fields for row in rows
    ):
        return False, (
            "Chrono cannot search when files were received because Google Drive "
            "shared-with-me time was not synchronized."
        )
    return True, None


def matches_plan(metadata: NormalizedDriveMetadata, plan: SearchPlan) -> bool:
    if plan.source and metadata.source != plan.source:
        return False
    if plan.event_type and metadata.event_type != plan.event_type:
        return False
    normalized_mime = normalize_mime_type(metadata.mime_type or "")
    allowed_mimes = {normalize_mime_type(value) for value in plan.mime_types}
    if plan.mime_type and normalized_mime != normalize_mime_type(plan.mime_type):
        return False
    if allowed_mimes and normalized_mime not in allowed_mimes:
        return False
    if plan.item_type == "folder" and not metadata.is_folder:
        return False
    if plan.item_type == "file" and metadata.is_folder:
        return False
    if plan.trashed is not None and metadata.trashed != plan.trashed:
        return False
    if plan.trashed is None and plan.intent in {"file_discovery", "content_search", "aggregate"} and metadata.trashed:
        return False
    title_filter = plan.filename or plan.title
    if title_filter and title_filter.casefold() not in metadata.title.casefold():
        return False
    if plan.start or plan.end:
        value = _date_value(metadata, plan.date_field)
        if value is None:
            return False
        if plan.start and value < plan.start:
            return False
        if plan.end and value > plan.end:
            return False
    people = []
    if plan.person_role == "owner":
        people = metadata.owners
    elif plan.person_role == "sharer":
        people = [metadata.sharing_user]
    elif plan.person_role == "last_modifier":
        people = [metadata.last_modifying_user]
    elif plan.person_role == "sender":
        people = [metadata.sender]
    if plan.person_role and not any(
        person_matches(person, name=plan.person_name, email=plan.person_email) for person in people
    ):
        return False
    return True


def _public_item(metadata: NormalizedDriveMetadata) -> StructuredItem:
    return StructuredItem(
        title=metadata.title,
        source=metadata.source,
        mime_type=metadata.mime_type,
        item_type="folder" if metadata.is_folder else "file",
        event_type=metadata.event_type,
        event_date=metadata.event_date,
        created_time=metadata.created_time,
        modified_time=metadata.modified_time,
        owner_display_names=[
            person.display_name for person in metadata.owners if person.display_name
        ],
        open_url=metadata.open_url,
    )


def _unsupported(plan: SearchPlan, reason: str) -> StructuredExecution:
    return StructuredExecution(
        answer=reason,
        intent="unsupported",
        retrieval_mode="structured",
        interpreted_filters=interpreted_filters(plan),
        items=[],
    )


def _memory_rows(db: Session, user_id: str, plan: SearchPlan) -> list[tuple[Memory, NormalizedDriveMetadata]]:
    query = db.query(Memory).filter(Memory.user_id == user_id)
    if plan.source:
        query = query.filter(Memory.source == plan.source)
    memories = query.order_by(Memory.event_date.desc(), Memory.title.asc()).all()
    return [(memory, normalize_memory(memory)) for memory in memories]


def _event_rows(
    db: Session, user_id: str, plan: SearchPlan
) -> list[tuple[GoogleDriveEvent, NormalizedDriveMetadata]]:
    query = db.query(GoogleDriveEvent).filter(GoogleDriveEvent.user_id == user_id)
    if plan.event_type:
        query = query.filter(GoogleDriveEvent.event_type == plan.event_type)
    events = query.order_by(
        GoogleDriveEvent.occurred_at.desc(), GoogleDriveEvent.received_at.desc()
    ).all()
    return [(event, normalize_drive_event(event)) for event in events]


def _latest_event_rows(
    db: Session, user_id: str, plan: SearchPlan
) -> list[tuple[GoogleDriveEvent, NormalizedDriveMetadata]]:
    rows = _event_rows(db, user_id, plan.model_copy(update={"event_type": None}))
    latest = []
    seen_file_ids: set[str] = set()
    for event, metadata in rows:
        if event.file_id in seen_file_ids:
            continue
        seen_file_ids.add(event.file_id)
        latest.append((event, metadata))
    return latest


def execute_structured_search(
    db: Session, *, user_id: str, plan: SearchPlan
) -> StructuredExecution:
    filters = interpreted_filters(plan)
    if plan.intent == "unsupported":
        return _unsupported(plan, plan.unsupported_reason or "Chrono cannot safely perform that search.")

    use_events = plan.intent == "event_history" or (
        plan.intent == "aggregate" and plan.event_type in {"deleted", "trashed", "restored", "moved"}
    )
    if use_events:
        rows = _event_rows(db, user_id, plan)
    else:
        rows = _memory_rows(db, user_id, plan)
    normalized_rows = [metadata for _row, metadata in rows]
    supported, reason = _role_supported(normalized_rows, plan)
    if not supported:
        return _unsupported(plan, reason or "Chrono does not have the required metadata.")

    matched = [(row, metadata) for row, metadata in rows if matches_plan(metadata, plan)]
    if plan.intent == "aggregate":
        if use_events:
            count = len(matched)
            noun = "Drive event" if count == 1 else "Drive events"
        else:
            count = len({(row.source, row.source_id) for row, _metadata in matched})
            noun = "file" if count == 1 else "files"
            if plan.item_type == "folder":
                noun = "folder" if count == 1 else "folders"
        return StructuredExecution(
            answer=f"Chrono found {count} {noun}.",
            intent="aggregate",
            retrieval_mode="structured",
            interpreted_filters=filters,
            items=[],
        )

    selected = matched[: plan.limit]
    if use_events and selected:
        current_urls = {
            memory.source_id: normalize_memory(memory).open_url
            for memory in db.query(Memory).filter(
                Memory.user_id == user_id,
                Memory.source == "google_drive",
                Memory.source_id.in_([row.file_id for row, _metadata in selected]),
            ).all()
        }
        items = [
            _public_item(metadata).model_copy(update={"open_url": current_urls.get(row.file_id)})
            for row, metadata in selected
        ]
    else:
        items = [_public_item(metadata) for _row, metadata in selected]
    if plan.intent == "event_history":
        noun = "Drive event" if len(items) == 1 else "Drive events"
    elif plan.intent == "current_timeline":
        noun = "current Drive item" if len(items) == 1 else "current Drive items"
    else:
        noun = "item" if len(items) == 1 else "items"
    answer = f"Chrono found {len(items)} {noun}."
    return StructuredExecution(
        answer=answer,
        intent=plan.intent,
        retrieval_mode="structured",
        interpreted_filters=filters,
        items=items,
    )
