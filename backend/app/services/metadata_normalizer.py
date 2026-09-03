from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.db.models import GoogleDriveEvent, Memory
from app.services.output_safety import safe_drive_open_url


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class NormalizedPerson:
    display_name: str | None = None
    email_address: str | None = None


@dataclass(frozen=True)
class NormalizedDriveMetadata:
    title: str
    source: str
    mime_type: str | None
    is_folder: bool
    trashed: bool
    event_type: str | None
    event_date: datetime | None
    created_time: datetime | None
    modified_time: datetime | None
    shared_with_me_time: datetime | None
    created_at: datetime | None
    occurred_at: datetime | None
    open_url: str | None = None
    owners: list[NormalizedPerson] = field(default_factory=list)
    sharing_user: NormalizedPerson | None = None
    last_modifying_user: NormalizedPerson | None = None
    sender: NormalizedPerson | None = None
    available_fields: frozenset[str] = frozenset()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sources(metadata: dict | None) -> list[dict]:
    root = metadata or {}
    sources = [root]
    raw = root.get("raw_change")
    if isinstance(raw, dict):
        sources.append(raw)
        file_data = raw.get("file")
        if isinstance(file_data, dict):
            sources.append(file_data)
    file_data = root.get("file")
    if isinstance(file_data, dict):
        sources.append(file_data)
    return sources


def _value(sources: list[dict], *aliases: str) -> tuple[Any, bool]:
    for source in sources:
        for alias in aliases:
            if alias in source:
                return source.get(alias), True
    return None, False


def _open_url(sources: list[dict], *additional: object) -> str | None:
    candidates = list(additional)
    for source in sources:
        candidates.extend(
            source.get(alias)
            for alias in ("webViewLink", "web_view_link", "file_url")
            if alias in source
        )
    for candidate in candidates:
        validated = safe_drive_open_url(candidate)
        if validated:
            return validated
    return None


def _person(value: Any) -> NormalizedPerson | None:
    if not isinstance(value, dict):
        return None
    name = value.get("displayName", value.get("display_name"))
    email = value.get("emailAddress", value.get("email_address"))
    if not name and not email:
        return None
    return NormalizedPerson(
        display_name=str(name) if name else None,
        email_address=str(email) if email else None,
    )


def _people(value: Any) -> list[NormalizedPerson]:
    values = value if isinstance(value, list) else [value]
    return [person for person in (_person(item) for item in values) if person is not None]


def normalize_memory(memory: Memory) -> NormalizedDriveMetadata:
    sources = _sources(memory.metadata_json)
    available: set[str] = set()

    name, name_present = _value(sources, "name", "title")
    mime_type, mime_present = _value(sources, "mime_type", "mimeType")
    created, created_present = _value(sources, "created_time", "createdTime")
    modified, modified_present = _value(sources, "modified_time", "modifiedTime")
    shared, shared_present = _value(sources, "shared_with_me_time", "sharedWithMeTime")
    folder, folder_present = _value(sources, "is_folder", "isFolder")
    trashed, trashed_present = _value(sources, "trashed")
    owners, owners_present = _value(sources, "owners")
    sharing_user, sharing_present = _value(sources, "sharing_user", "sharingUser")
    modifier, modifier_present = _value(sources, "last_modifying_user", "lastModifyingUser")

    for field_name, present in (
        ("name", name_present), ("mime_type", mime_present),
        ("created_time", created_present), ("modified_time", modified_present),
        ("shared_with_me_time", shared_present), ("is_folder", folder_present),
        ("trashed", trashed_present), ("owners", owners_present),
        ("sharing_user", sharing_present), ("last_modifying_user", modifier_present),
    ):
        if present:
            available.add(field_name)
    if memory.sender:
        available.add("sender")

    normalized_mime = str(mime_type) if mime_type else None
    is_folder = bool(folder) if folder_present else normalized_mime == FOLDER_MIME_TYPE
    return NormalizedDriveMetadata(
        title=str(name or memory.title),
        source=memory.source,
        mime_type=normalized_mime,
        is_folder=is_folder,
        trashed=bool(trashed) if trashed_present else memory.event_type == "trashed",
        event_type=memory.event_type,
        event_date=_parse_datetime(memory.event_date),
        created_time=_parse_datetime(created),
        modified_time=_parse_datetime(modified),
        shared_with_me_time=_parse_datetime(shared),
        created_at=_parse_datetime(memory.created_at),
        occurred_at=_parse_datetime(memory.event_date),
        open_url=_open_url(sources, memory.file_url),
        owners=_people(owners),
        sharing_user=_person(sharing_user),
        last_modifying_user=_person(modifier),
        sender=NormalizedPerson(display_name=memory.sender) if memory.sender else None,
        available_fields=frozenset(available),
    )


def normalize_drive_event(event: GoogleDriveEvent) -> NormalizedDriveMetadata:
    sources = _sources(event.payload)
    available: set[str] = set()
    created, created_present = _value(sources, "created_time", "createdTime")
    modified, modified_present = _value(sources, "modified_time", "modifiedTime")
    shared, shared_present = _value(sources, "shared_with_me_time", "sharedWithMeTime")
    owners, owners_present = _value(sources, "owners")
    sharing_user, sharing_present = _value(sources, "sharing_user", "sharingUser")
    modifier, modifier_present = _value(sources, "last_modifying_user", "lastModifyingUser")
    trashed, trashed_present = _value(sources, "trashed")
    for field_name, present in (
        ("created_time", created_present), ("modified_time", modified_present),
        ("shared_with_me_time", shared_present), ("owners", owners_present),
        ("sharing_user", sharing_present), ("last_modifying_user", modifier_present),
        ("trashed", trashed_present),
    ):
        if present:
            available.add(field_name)
    return NormalizedDriveMetadata(
        title=event.name or "Untitled Drive item",
        source="google_drive",
        mime_type=event.mime_type,
        is_folder=event.is_folder or event.mime_type == FOLDER_MIME_TYPE,
        trashed=bool(trashed) if trashed_present else event.event_type == "trashed",
        event_type=event.event_type,
        event_date=_parse_datetime(event.occurred_at),
        created_time=_parse_datetime(created),
        modified_time=_parse_datetime(modified),
        shared_with_me_time=_parse_datetime(shared),
        created_at=_parse_datetime(event.received_at),
        occurred_at=_parse_datetime(event.occurred_at),
        open_url=_open_url(sources),
        owners=_people(owners),
        sharing_user=_person(sharing_user),
        last_modifying_user=_person(modifier),
        available_fields=frozenset(available),
    )


def person_matches(person: NormalizedPerson | None, *, name: str | None, email: str | None) -> bool:
    if person is None:
        return False
    if email and (person.email_address or "").casefold() != email.casefold():
        return False
    if name and name.casefold() not in (person.display_name or "").casefold():
        return False
    return bool(name or email)
