from dataclasses import asdict, dataclass
from typing import Callable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.db.models import GoogleDriveEvent, Memory, User


class OwnershipClaimError(Exception):
    pass


@dataclass(frozen=True)
class ClaimCounts:
    memories: int
    drive_events: int


@dataclass(frozen=True)
class ClaimResult:
    mode: str
    target_user_id: str
    before: ClaimCounts
    updated: ClaimCounts
    after: ClaimCounts

    def as_dict(self) -> dict:
        return asdict(self)


def _legacy_event_filter():
    return or_(GoogleDriveEvent.user_id == "default", GoogleDriveEvent.user_id.is_(None))


def _counts(db: Session) -> ClaimCounts:
    memories = db.query(Memory).filter(Memory.user_id == "default").count()
    events = db.query(GoogleDriveEvent).filter(_legacy_event_filter()).count()
    return ClaimCounts(memories=memories, drive_events=events)


def claim_default_user_data(
    db: Session,
    *,
    email: str,
    apply: bool,
    before_commit: Callable[[], None] | None = None,
) -> ClaimResult:
    """Atomically claim legacy ownership without recreating any content rows."""
    normalized_email = email.strip().casefold()
    if not normalized_email:
        raise OwnershipClaimError("A target email is required")

    transaction = db.begin_nested() if db.in_transaction() else db.begin()
    with transaction:
        users = db.query(User).filter(func.lower(User.email) == normalized_email).all()
        if len(users) != 1:
            raise OwnershipClaimError(
                "The target must match exactly one existing Google-authenticated user"
            )
        target = users[0]
        if not target.is_active:
            raise OwnershipClaimError("The target user is inactive")
        target_id = str(target.id)
        before = _counts(db)

        existing = aliased(Memory)
        conflicts = (
            db.query(Memory.id)
            .join(
                existing,
                (existing.user_id == target_id)
                & (existing.source == Memory.source)
                & (existing.source_id == Memory.source_id),
            )
            .filter(Memory.user_id == "default")
            .count()
        )
        if conflicts:
            raise OwnershipClaimError(
                "Claim refused because the target user already owns conflicting source records"
            )

        if not apply:
            return ClaimResult(
                mode="dry-run",
                target_user_id=target_id,
                before=before,
                updated=ClaimCounts(0, 0),
                after=before,
            )

        updated_memories = (
            db.query(Memory)
            .filter(Memory.user_id == "default")
            .update({Memory.user_id: target_id}, synchronize_session=False)
        )
        updated_events = (
            db.query(GoogleDriveEvent)
            .filter(_legacy_event_filter())
            .update({GoogleDriveEvent.user_id: target_id}, synchronize_session=False)
        )
        db.flush()
        if before_commit:
            before_commit()
        after = _counts(db)
        return ClaimResult(
            mode="apply",
            target_user_id=target_id,
            before=before,
            updated=ClaimCounts(updated_memories, updated_events),
            after=after,
        )
