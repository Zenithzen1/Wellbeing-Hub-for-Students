"""Pydantic request/response models, one group per router."""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field

# --- events (Divyam) -------------------------------------------------------------------------
# Times must carry a UTC offset, e.g. "2026-12-03T16:00:00+04:00"; they are stored in UTC.


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: AwareDatetime
    end: AwareDatetime
    location: str = Field(default="", max_length=200)
    capacity: int = Field(ge=1, le=10000)
    tags: list[str] = Field(default_factory=list, max_length=15)


class EventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    location: str | None = Field(default=None, max_length=200)
    capacity: int | None = Field(default=None, ge=1, le=10000)
    tags: list[str] | None = Field(default=None, max_length=15)


class EventOut(BaseModel):
    id: int
    title: str
    start: datetime
    end: datetime
    location: str
    capacity: int
    tags: list[str]
    registered: int
    waitlisted: int
    spots_left: int
    my_status: str | None = None  # students only: "registered" | "waitlisted" | null


class RegistrationOut(BaseModel):
    event_id: int
    status: str  # "registered" | "waitlisted"


# --- notifications (Divyam) ------------------------------------------------------------------


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str
    payload: dict
    send_at: datetime
    read: bool


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=5000)
    send_at: AwareDatetime | None = None  # null = now


class AnnouncementOut(BaseModel):
    id: int
    title: str
    body: str
    send_at: datetime
    status: str


class DeadLetterOut(BaseModel):
    id: int
    kind: str
    title: str
    attempts: int
    last_attempt_at: datetime
    last_error: str | None
