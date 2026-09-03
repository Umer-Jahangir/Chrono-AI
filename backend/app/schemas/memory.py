from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MemoryCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str
    source_id: str
    title: str
    content: str
    event_type: str
    event_date: datetime
    sender: str | None = None
    file_url: str | None = None
    metadata_json: dict | None = None


class MemoryResponse(MemoryCreate):
    id: UUID
    user_id: str
    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )
