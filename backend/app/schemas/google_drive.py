from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GoogleDriveEventIn(BaseModel):
    # Ignore, and therefore never persist, arbitrary ownership fields supplied
    # by an automation payload. Ownership is resolved server-side.
    model_config = ConfigDict(extra="ignore")

    source: Literal["google_drive"] = "google_drive"
    drive_id: str = "my-drive"
    change_id: str = Field(min_length=1, max_length=255)
    event_type: Literal["created", "modified", "moved", "deleted", "trashed", "restored"]
    file_id: str = Field(min_length=1, max_length=255)
    name: str | None = None
    mime_type: str | None = None
    is_folder: bool = False
    removed: bool = False
    occurred_at: datetime
    parents: list[str] = Field(default_factory=list)
    previous_parents: list[str] = Field(default_factory=list)
    web_view_link: str | None = None
    owners: list[dict[str, Any]] = Field(default_factory=list)
    raw_change: dict[str, Any]


class GoogleDriveEventOut(BaseModel):
    accepted: bool
    duplicate: bool
    event_id: str
