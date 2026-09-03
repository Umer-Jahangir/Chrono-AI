import hmac
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import GoogleDriveEvent, Memory, MemoryChunk, User
from app.schemas.google_drive import GoogleDriveEventIn, GoogleDriveEventOut
from app.services.content_extractor import UnsupportedContentType, extract_text
from app.services.memory_indexer import index_memory
from app.services.ai_provider import preferred_embedding_spec, preferred_generation_provider
from app.services.embedding_reindexer import reindex_embeddings
from app.services.auth import get_current_user
from app.api.timeline import current_memories_for_events, event_public_item


router = APIRouter(prefix="/integrations/google-drive", tags=["google-drive"])


def verify_n8n_secret(x_n8n_secret: str | None = Header(default=None)) -> None:
    expected = settings.N8N_WEBHOOK_SECRET
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Drive webhook authentication is not configured",
        )
    if not x_n8n_secret or not hmac.compare_digest(x_n8n_secret, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid n8n secret")


def resolve_n8n_owner(
    _: None = Depends(verify_n8n_secret),
    db: Session = Depends(get_db),
) -> str:
    """Resolve the single-user Drive owner without trusting webhook payload data."""
    configured = settings.CHRONO_N8N_OWNER_USER_ID.strip()
    if configured:
        try:
            owner = db.get(User, UUID(configured))
        except Exception:
            owner = None
        if owner is None or not owner.is_active:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google Drive ownership mapping is unavailable",
            )
        return str(owner.id)
    if settings.ALLOW_LEGACY_DEFAULT_USER:
        return "default"
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Google Drive ownership mapping is not configured",
    )


@router.post("/events", response_model=GoogleDriveEventOut)
def receive_google_drive_event(
    event: GoogleDriveEventIn,
    db: Session = Depends(get_db),
    owner_user_id: str = Depends(resolve_n8n_owner),
) -> GoogleDriveEventOut:
    event = _classify_against_memory(db, event, owner_user_id)
    row = GoogleDriveEvent(
        user_id=owner_user_id,
        drive_id=event.drive_id,
        change_id=event.change_id,
        event_type=event.event_type,
        file_id=event.file_id,
        name=event.name,
        mime_type=event.mime_type,
        is_folder=event.is_folder,
        removed=event.removed,
        occurred_at=event.occurred_at,
        payload=event.model_dump(mode="json"),
    )
    db.add(row)
    try:
        _apply_memory_lifecycle(db, event, owner_user_id)
        db.commit()
        db.refresh(row)
        return GoogleDriveEventOut(accepted=True, duplicate=False, event_id=str(row.id))
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(GoogleDriveEvent)
            .filter_by(drive_id=event.drive_id, change_id=event.change_id)
            .one()
        )
        return GoogleDriveEventOut(accepted=True, duplicate=True, event_id=str(existing.id))


def _classify_against_memory(
    db: Session, event: GoogleDriveEventIn, owner_user_id: str
) -> GoogleDriveEventIn:
    """Use the persisted baseline to identify a move on the first live change."""
    if event.event_type != "modified" or event.removed:
        return event
    memory = _find_memory(db, event.file_id, owner_user_id)
    previous = (memory.metadata_json or {}) if memory else {}
    previous_parents = previous.get("parents") or []
    if memory and sorted(previous_parents) != sorted(event.parents):
        return event.model_copy(update={"event_type": "moved", "previous_parents": previous_parents})
    return event


def _find_memory(db: Session, file_id: str, owner_user_id: str) -> Memory | None:
    return (
        db.query(Memory)
        .filter(
            Memory.user_id == owner_user_id,
            Memory.source == "google_drive",
            Memory.source_id == file_id,
        )
        .one_or_none()
    )


def _apply_memory_lifecycle(
    db: Session, event: GoogleDriveEventIn, owner_user_id: str
) -> None:
    memory = _find_memory(db, event.file_id, owner_user_id)
    if event.event_type == "deleted":
        if memory:
            db.delete(memory)
        return

    metadata = event.model_dump(mode="json")
    if memory is None:
        db.add(Memory(
            user_id=owner_user_id,
            source="google_drive",
            source_id=event.file_id,
            title=event.name or event.file_id,
            content="",
            event_type=event.event_type,
            event_date=event.occurred_at,
            file_url=event.web_view_link,
            metadata_json=metadata,
        ))
    else:
        if event.event_type == "trashed":
            db.query(MemoryChunk).filter(MemoryChunk.memory_id == memory.id).delete(
                synchronize_session=False
            )
            memory.content = ""
        memory.title = event.name or memory.title
        memory.event_type = event.event_type
        memory.event_date = event.occurred_at
        memory.file_url = event.web_view_link or memory.file_url
        memory.metadata_json = metadata


@router.post("/content")
async def receive_google_drive_content(
    event_json: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    owner_user_id: str = Depends(resolve_n8n_owner),
):
    try:
        event = GoogleDriveEventIn.model_validate(json.loads(event_json))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid event_json: {exc}") from exc

    data = await file.read(settings.MAX_INGEST_FILE_BYTES + 1)
    if len(data) > settings.MAX_INGEST_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds ingestion size limit")
    try:
        content = extract_text(data, file.filename or event.name or "file", file.content_type or event.mime_type)
    except UnsupportedContentType as exc:
        return {"accepted": True, "indexed": False, "reason": str(exc), "file_id": event.file_id}
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Content extraction failed: {exc}") from exc

    memory = _find_memory(db, event.file_id, owner_user_id)
    if memory is None:
        memory = Memory(
            user_id=owner_user_id,
            source="google_drive",
            source_id=event.file_id,
            title=event.name or file.filename or event.file_id,
            content=content,
            event_type=event.event_type,
            event_date=event.occurred_at,
            file_url=event.web_view_link,
            metadata_json=event.model_dump(mode="json"),
        )
        db.add(memory)
    else:
        memory.content = content
        memory.title = event.name or memory.title
        memory.event_type = event.event_type
        memory.event_date = event.occurred_at
        memory.file_url = event.web_view_link or memory.file_url
        memory.metadata_json = event.model_dump(mode="json")
    db.flush()
    index_stats = index_memory(db, memory)
    db.commit()
    db.refresh(memory)
    return {
        "accepted": True,
        "indexed": True,
        "memory_id": str(memory.id),
        "characters": len(content),
        **index_stats,
    }


@router.get("/events")
def list_google_drive_events(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(GoogleDriveEvent)
        .filter(GoogleDriveEvent.user_id == str(current_user.id))
        .order_by(GoogleDriveEvent.received_at.desc())
        .limit(limit)
        .all()
    )
    current = current_memories_for_events(db, str(current_user.id), rows)
    return {
        "count": len(rows),
        "items": [
            event_public_item(row, current.get(row.file_id)).model_dump(mode="json")
            for row in rows
        ],
    }


@router.get("/status")
def google_drive_sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_id = str(current_user.id)
    event_count = (
        db.query(func.count(GoogleDriveEvent.id))
        .filter(GoogleDriveEvent.user_id == user_id)
        .scalar()
        or 0
    )
    memory_count = (
        db.query(func.count(Memory.id))
        .filter(Memory.user_id == user_id, Memory.source == "google_drive")
        .scalar()
        or 0
    )
    chunk_scope = db.query(MemoryChunk).join(Memory).filter(Memory.user_id == user_id)
    chunk_count = chunk_scope.count()
    embedded_count = chunk_scope.filter(MemoryChunk.embedding.is_not(None)).count()
    preferred_spec = preferred_embedding_spec()
    generation_provider = preferred_generation_provider()
    matching_embedded_count = 0
    if preferred_spec:
        matching_embedded_count = (
            db.query(func.count(MemoryChunk.id))
            .join(Memory)
            .filter(
                Memory.user_id == user_id,
                MemoryChunk.embedding.is_not(None),
                MemoryChunk.embedding_provider == preferred_spec.provider,
                MemoryChunk.embedding_model == preferred_spec.model,
                MemoryChunk.embedding_dimensions == preferred_spec.dimensions,
            )
            .scalar()
            or 0
        )
    last_event = (
        db.query(GoogleDriveEvent)
        .filter(GoogleDriveEvent.user_id == user_id)
        .order_by(GoogleDriveEvent.received_at.desc())
        .first()
    )
    return {
        "status": "ready",
        "drive_events": event_count,
        "indexed_items": memory_count,
        "memory_chunks": chunk_count,
        "embedded_chunks": embedded_count,
        "active_embedding_provider": preferred_spec.provider if preferred_spec else None,
        "active_embedding_model": preferred_spec.model if preferred_spec else None,
        "active_embedding_dimensions": preferred_spec.dimensions if preferred_spec else None,
        "active_answer_provider": generation_provider["provider"] if generation_provider else None,
        "active_answer_model": generation_provider["model"] if generation_provider else None,
        "active_signature_chunks": matching_embedded_count,
        "embedding_regeneration_required": bool(
            preferred_spec and chunk_count != matching_embedded_count
        ),
        "last_event_received_at": last_event.received_at if last_event else None,
        "last_event_type": last_event.event_type if last_event else None,
    }


@router.post("/reindex")
def reindex_google_drive_memories(
    embed: bool = Query(default=True),
    missing_only: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not embed:
        raise HTTPException(status_code=400, detail="Embedding reindex requires embed=true")
    safe_errors: list[dict] = []
    result = reindex_embeddings(
        db,
        user_id=str(current_user.id),
        missing_only=missing_only,
        report=safe_errors.append,
    )
    return {**result, "error_details": safe_errors}
