from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.rag import StructuredItem


EventType = Literal["created", "modified", "moved", "trashed", "restored", "deleted"]


class DashboardDay(BaseModel):
    date: date
    total: int = 0
    created: int = 0
    modified: int = 0
    moved: int = 0
    trashed: int = 0
    restored: int = 0
    deleted: int = 0


class DashboardSummaryResponse(BaseModel):
    range: Literal["this_week", "last_7_days", "last_30_days"]
    timezone: str
    start: datetime
    end: datetime
    event_count: int
    event_counts: dict[EventType, int]
    days: list[DashboardDay] = Field(default_factory=list)
    recent_items: list[StructuredItem] = Field(default_factory=list)
