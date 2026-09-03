from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal[
        "content_question",
        "content_search",
        "file_discovery",
        "current_timeline",
        "event_history",
        "aggregate",
        "unsupported",
    ]
    query_text: str | None = None
    source: str | None = None
    event_type: str | None = None
    mime_type: str | None = None
    item_type: Literal["file", "folder"] | None = None
    title: str | None = None
    filename: str | None = None
    trashed: bool | None = None
    person_name: str | None = None
    person_email: str | None = None
    person_role: Literal[
        "owner", "sharer", "last_modifier", "activity_actor", "sender"
    ] | None = None
    start: datetime | None = None
    end: datetime | None = None
    date_field: Literal[
        "event_date",
        "created_time",
        "modified_time",
        "shared_with_me_time",
        "created_at",
        "occurred_at",
    ] | None = None
    aggregate: Literal["count"] | None = None
    limit: int = Field(default=10, ge=1, le=50)
    unsupported_reason: str | None = None


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(min_length=2, max_length=4000)
    limit: int = Field(default=8, ge=1, le=50)
    source: str | None = None
    event_type: str | None = None
    mime_type: str | None = None
    start: datetime | None = None
    end: datetime | None = None


class AskSource(BaseModel):
    citation: int
    title: str
    excerpt: str
    event_date: datetime
    open_url: str | None = None
    passages: list["AskPassage"] = Field(default_factory=list)


class AskPassage(BaseModel):
    citation: int
    excerpt: str


class StructuredItem(BaseModel):
    title: str
    source: str
    mime_type: str | None = None
    item_type: Literal["file", "folder"]
    event_type: str | None = None
    event_date: datetime | None = None
    created_time: datetime | None = None
    modified_time: datetime | None = None
    owner_display_names: list[str] = Field(default_factory=list)
    excerpt: str | None = None
    open_url: str | None = None


class TimelineResponse(BaseModel):
    view: Literal["current", "history"]
    count: int
    items: list[StructuredItem] = Field(default_factory=list)


class AskResponse(BaseModel):
    answer: str
    retrieval_mode: str
    sources: list[AskSource] = Field(default_factory=list)
    intent: str | None = None
    interpreted_filters: dict = Field(default_factory=dict)
    items: list[StructuredItem] = Field(default_factory=list)
