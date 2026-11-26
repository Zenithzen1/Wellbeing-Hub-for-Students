"""SQLAlchemy tables (plan section 10).

Identity zone:    accounts, counsellors, identity_vault, audit_log
Operational zone: availability, bookings, waitlist_entries, offers, events, registrations,
                  tags, item_tags, resources, interests, engagements, notifications

Rule: no foreign key goes from the operational zone to `accounts`; operational rows
carry the HMAC pseudonym only.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes in, timezone-aware UTC datetimes out.

    SQLite has no time zones, so values are stored as naive UTC and tagged UTC again on load.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime needs a timezone-aware datetime")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


# TODO(all, Day 1): define the other tables here.


# --- Counsellors, availability, bookings (plan section 4; owner: Aditya) -------------------

class Counsellor(Base):
    """Identity zone. One row per counsellor account.

    account_id is the counsellor's row in `accounts`.
    TODO(Rithwik): make it ForeignKey("accounts.id") once the Account table exists.
    """

    __tablename__ = "counsellors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    specialties: Mapped[str] = mapped_column(String(300), default="")  # comma-separated, e.g. "anxiety,study"


class Availability(Base):
    """A counsellor's time. kind "open" = a window students can book inside;
    kind "blocked" = busy time with no session (e.g. a staff meeting). Half-open [start, end)."""

    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counsellor_id: Mapped[int] = mapped_column(ForeignKey("counsellors.id", ondelete="CASCADE"), index=True)
    start: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    kind: Mapped[str] = mapped_column(String(8))
    note: Mapped[str] = mapped_column(String(200), default="")


class Booking(Base):
    """A counselling session, half-open [start, end). Carries the student's pseudonym only.

    status:       active | cancelled | completed | no_show
    revealed:     the student ticked "share my name with my counsellor for this session"
    enc_identity: their name and email, encrypted with the server key, only when revealed
    """

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counsellor_id: Mapped[int] = mapped_column(ForeignKey("counsellors.id", ondelete="CASCADE"), index=True)
    pseudonym: Mapped[str] = mapped_column(String(64), index=True)
    start: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    reason: Mapped[str] = mapped_column(String(32))
    first_visit: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    revealed: Mapped[bool] = mapped_column(Boolean, default=False)
    enc_identity: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    cancelled_by: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "student" | "counsellor"


# --- Waitlist and offers (plan section 5; owner: Aditya) ---------------------------------

class WaitlistEntry(Base):
    """One student in one line. counsellor_id NULL = the "any counsellor" line.

    tier:   0 = needs to talk within 48 hours (or aged), 1 = normal. Heap key = (tier, joined_at, id).
    misses: offers that timed out; the second one removes the entry.
    status: waiting | offered | booked | left | removed
    """

    __tablename__ = "waitlist_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counsellor_id: Mapped[int | None] = mapped_column(ForeignKey("counsellors.id", ondelete="CASCADE"),
                                                      index=True, nullable=True)
    pseudonym: Mapped[str] = mapped_column(String(64), index=True)
    tier: Mapped[int] = mapped_column(Integer)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime)
    misses: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="waiting", index=True)


class Offer(Base):
    """Freed time offered to one waitlisted student, held for them until expires_at.

    status: open | accepted | declined | expired | withdrawn (the student left the waitlist)
    """

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    waitlist_id: Mapped[int] = mapped_column(ForeignKey("waitlist_entries.id", ondelete="CASCADE"), index=True)
    counsellor_id: Mapped[int] = mapped_column(ForeignKey("counsellors.id", ondelete="CASCADE"))
    start: Mapped[datetime] = mapped_column(UTCDateTime)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"), nullable=True)


# --- Events and workshops (plan section 6; owner: Divyam) ------------------------------

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    start: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end: Mapped[datetime] = mapped_column(UTCDateTime)
    location: Mapped[str] = mapped_column(String(200), default="")
    capacity: Mapped[int] = mapped_column(Integer)


class Registration(Base):
    """One row per (event, student). status: registered | waitlisted | cancelled.
    position orders the waitlisted rows of an event (FIFO), and is rebuilt into its queue."""

    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("event_id", "pseudonym"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    pseudonym: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    position: Mapped[int] = mapped_column(Integer, default=0)


# --- Tags (shared with recommendations, plan section 8) ---------------------------------

class Tag(Base):
    """The curated interest tags (Sleep, Exams, ...). Names are stored lower-case."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class ItemTag(Base):
    """Item-tag edge. item uses the graph's node ids: "e:<event id>" or "r:<resource id>"."""

    __tablename__ = "item_tags"

    item: Mapped[str] = mapped_column(String(32), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


# --- Notifications (plan section 7; owner: Divyam) --------------------------------------

class Notification(Base):
    """A message that goes through the timed heap and then the delivery queue.

    recipient: a student's pseudonym, "acct:<account id>" for staff, or "all" (announcement).
    status:    pending -> sent | dead (4th failure, dead-letter list) | skipped (missed while the
               server was off for over an hour) | cancelled (e.g. the booking was cancelled).
    ref:       what created it, e.g. "booking:12", so its reminders can be cancelled together.
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient: Mapped[str] = mapped_column(String(80), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[str] = mapped_column(Text, default="{}")  # JSON: {"title", "body", ...}
    send_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ref: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class NotificationRead(Base):
    """Who has read which notification (works for announcements sent to "all" too)."""

    __tablename__ = "notification_reads"

    notification_id: Mapped[int] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True)
    recipient: Mapped[str] = mapped_column(String(80), primary_key=True)
