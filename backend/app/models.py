"""SQLAlchemy tables (plan section 10).

Identity zone:    accounts, counsellors, identity_vault, audit_log
Operational zone: availability, bookings, waitlist_entries, offers, events, registrations,
                  tags, item_tags, resources, interests, engagements, notifications

Rule: no foreign key goes from the operational zone to `accounts`; operational rows
carry the HMAC pseudonym only.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, TypeDecorator, UniqueConstraint
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
