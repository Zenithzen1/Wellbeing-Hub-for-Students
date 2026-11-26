"""Pydantic request/response models, one group per router."""

from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

# --- booking (Aditya) ------------------------------------------------------------------------
# Same time rules as events: send a UTC offset, e.g. "2026-12-01T10:00:00+04:00".

Reason = Literal["academic_stress", "anxiety", "low_mood", "relationships", "sleep", "other"]


class CounsellorOut(BaseModel):
    id: int
    display_name: str
    specialties: list[str]


class IntervalOut(BaseModel):
    start: datetime
    end: datetime


class FreeDayOut(BaseModel):
    counsellor_id: int
    day: date               # Dubai-time date
    session_minutes: int
    open: list[IntervalOut]  # the counsellor's windows that day
    busy: list[IntervalOut]  # taken or blocked (no detail)
    starts: list[datetime]   # every start time where a session fits


class AvailabilityIn(BaseModel):
    start: AwareDatetime
    end: AwareDatetime
    kind: Literal["open", "blocked"] = "open"
    note: str = Field(default="", max_length=200)


class AvailabilityOut(BaseModel):
    id: int
    start: datetime
    end: datetime
    kind: str
    note: str


class BookingIn(BaseModel):
    counsellor_id: int
    start: AwareDatetime
    reason: Reason
    first_visit: bool = False  # 60 minutes instead of 45
    reveal: bool = False       # share my name with my counsellor for this session


class BookingOut(BaseModel):
    id: int
    counsellor_id: int
    counsellor_name: str
    start: datetime
    end: datetime
    reason: str
    first_visit: bool
    status: str  # active | cancelled | completed | no_show
    revealed: bool


class SessionOut(BaseModel):
    """Counsellor view of a booking."""

    id: int
    start: datetime
    end: datetime
    student: str  # pseudonym tag, e.g. "#47C32E"
    reason: str
    first_visit: bool
    status: str
    revealed: bool
    identity: str | None = None  # only when the student opted in


class BookingPatch(BaseModel):
    status: Literal["completed", "no_show"]


# --- waitlist (Aditya) -----------------------------------------------------------------------


class WaitlistIn(BaseModel):
    counsellor_id: int | None = None  # null = the "any counsellor" line
    urgent: bool = False              # "I need to talk to someone within 48 hours"


class OfferOut(BaseModel):
    id: int
    counsellor_id: int
    counsellor_name: str
    start: datetime
    end: datetime
    expires_at: datetime
    status: str


class WaitlistOut(BaseModel):
    id: int
    counsellor_id: int | None
    counsellor_name: str | None
    urgent: bool
    joined_at: datetime
    status: str  # waiting | offered
    misses: int
    ahead: int   # people before you in this line
    offer: OfferOut | None = None


class OfferAcceptIn(BaseModel):
    reason: Reason = "other"
    reveal: bool = False


class WaitlistCountsOut(BaseModel):
    urgent: int
    normal: int
    any_urgent: int
    any_normal: int

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
