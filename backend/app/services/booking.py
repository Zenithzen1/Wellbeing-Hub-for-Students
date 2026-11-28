"""Booking: per-counsellor lock, interval-tree overlap check, write-through, cancellation. Owner: Aditya.

Plan section 4.
* Each counsellor has two IntervalTrees (our AVL subclass that keeps the max end of every subtree):
      _open[cid]  the open windows students may book inside (windows never overlap each other),
      _busy[cid]  every busy interval: sessions, blocked time and waitlist holds.
  The plan's intervals are half-open [start, end); the tree's are closed. Times are whole epoch seconds
  and [s, e) is stored as the closed (s, e - 1). For whole numbers that is exactly the half-open test,
  so 10:00-10:45 and 10:45-11:30 touch but do not clash.
  Values: _open -> availability id; _busy -> ("booking" | "blocked" | "hold", row id).
* Booking: inside the counsellor's lock, check the tree, then BEGIN IMMEDIATE, re-check with SQL, INSERT,
  COMMIT, and only then insert into the tree (write-through). T-24h and T-1h reminders are scheduled and
  open grids get a slot_taken SSE.
* Cancellation reverses this and offers the freed time to the waitlist before anyone else can see it.
* If a tree update fails after the commit, that counsellor's trees are reloaded from the database.

Errors: CounsellorNotFound, BookingNotFound, AvailabilityNotFound (-> 404), SlotTaken (-> 409),
ValueError (-> 400).
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.ds import HashMap, IntervalTree
from app.models import Availability, Booking, Counsellor, Offer
from app.services import notify

log = logging.getLogger(__name__)

SESSION = timedelta(minutes=45)
FIRST_VISIT = timedelta(minutes=60)
GRID_SECONDS = 15 * 60                 # sessions start on a quarter hour (Dubai is UTC+4, so UTC marks match)
MAX_AHEAD = timedelta(days=60)         # how far ahead a session can be booked
MAX_WINDOW = timedelta(hours=24)       # longest single availability window
REASONS = ("academic_stress", "anxiety", "low_mood", "relationships", "sleep", "other")


class CounsellorNotFound(KeyError):
    pass


class BookingNotFound(KeyError):
    pass


class AvailabilityNotFound(KeyError):
    pass


class SlotTaken(Exception):
    """The time overlaps something already there (-> 409)."""


@dataclass
class CounsellorRecord:
    id: int
    account_id: int
    display_name: str
    specialties: tuple[str, ...]


_lock = threading.RLock()  # guards the maps and trees below (short sections only)
_counsellors = HashMap()   # counsellor id -> CounsellorRecord
_by_account = HashMap()    # account id -> counsellor id
_open = HashMap()          # counsellor id -> IntervalTree of open windows
_busy = HashMap()          # counsellor id -> IntervalTree of sessions, blocked time and holds
_locks = HashMap()         # counsellor id -> RLock: one writer per counsellor (check, commit, insert)


# --- small helpers --------------------------------------------------------------------------------

def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, timezone.utc)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("times need a UTC offset, e.g. 2026-12-01T10:00:00+04:00")
    return dt.astimezone(timezone.utc)


def _when(start: datetime) -> str:
    return clock.to_local(start).strftime("%a %d %b, %H:%M")


def tag(pseudonym: str) -> str:
    """What counsellors see instead of a name, e.g. "#47C32E"."""
    return "#" + pseudonym[:6].upper()


def lock_for(counsellor_id: int) -> threading.RLock:
    """The counsellor's write lock. Re-entrant, so cancel -> waitlist offer -> hold can nest."""
    with _lock:
        lk = _locks.get(counsellor_id)
        if lk is None:
            lk = threading.RLock()
            _locks.put(counsellor_id, lk)
        return lk


# --- startup ----------------------------------------------------------------------------------------

def _load(db: Session, counsellor_id: int) -> tuple[IntervalTree, IntervalTree]:
    """One counsellor's trees from SQLite: open windows; future sessions, blocks and open holds."""
    now = clock.now()
    open_tree, busy = IntervalTree(), IntervalTree()
    for a in db.scalars(select(Availability).where(Availability.counsellor_id == counsellor_id,
                                                   Availability.end > now)):
        if a.kind == "open":
            open_tree.insert(_ts(a.start), _ts(a.end) - 1, a.id)
        else:
            busy.insert(_ts(a.start), _ts(a.end) - 1, ("blocked", a.id))
    for b in db.scalars(select(Booking).where(Booking.counsellor_id == counsellor_id, Booking.status == "active",
                                              Booking.end > now)):
        busy.insert(_ts(b.start), _ts(b.end) - 1, ("booking", b.id))
    for o in db.scalars(select(Offer).where(Offer.counsellor_id == counsellor_id, Offer.status == "open")):
        busy.insert(_ts(o.start), _ts(o.end) - 1, ("hold", o.id))
    return open_tree, busy


def rebuild(db: Session) -> None:
    """Rebuild the counsellor list and every interval tree from SQLite (plan section 10)."""
    global _counsellors, _by_account, _open, _busy
    counsellors, by_account, open_, busy = HashMap(), HashMap(), HashMap(), HashMap()
    for row in db.scalars(select(Counsellor)):
        counsellors.put(row.id, _record(row))
        by_account.put(row.account_id, row.id)
        o, b = _load(db, row.id)
        open_.put(row.id, o)
        busy.put(row.id, b)
    with _lock:
        _counsellors, _by_account, _open, _busy = counsellors, by_account, open_, busy


def _record(row: Counsellor) -> CounsellorRecord:
    specialties = tuple(s.strip() for s in (row.specialties or "").split(",") if s.strip())
    return CounsellorRecord(row.id, row.account_id, row.display_name, specialties)


# Write-through: every change is committed to the database first, then copied into the tree.
# If the tree update ever fails, the database is right, so we rebuild that counsellor's trees from it.

def _tree(which: str, counsellor_id: int) -> IntervalTree:
    """The counsellor's "open" tree (windows) or "busy" tree (sessions, blocks, holds)."""
    return _open.get(counsellor_id) if which == "open" else _busy.get(counsellor_id)


def _tree_add(db: Session, counsellor_id: int, which: str, start: int, end: int, value) -> None:
    """Add the half-open interval [start, end) (epoch seconds) to a tree. Stored closed as (start, end - 1)."""
    try:
        with _lock:
            _tree(which, counsellor_id).insert(start, end - 1, value)
    except Exception:
        _reload(db, counsellor_id)


def _tree_remove(db: Session, counsellor_id: int, which: str, start: int, end: int) -> None:
    """Remove [start, end) from a tree, if it is there."""
    try:
        with _lock:
            tree = _tree(which, counsellor_id)
            if (start, end - 1) in tree:
                tree.delete(start, end - 1)
    except Exception:
        _reload(db, counsellor_id)


def _reload(db: Session, counsellor_id: int) -> None:
    log.exception("interval tree update failed for counsellor %s; reloading it from the database", counsellor_id)
    open_tree, busy_tree = _load(db, counsellor_id)
    with _lock:
        _open.put(counsellor_id, open_tree)
        _busy.put(counsellor_id, busy_tree)


# --- counsellors -------------------------------------------------------------------------------------

def add_counsellor(db: Session, account_id: int, display_name: str,
                   specialties: tuple[str, ...] | list[str] = ()) -> CounsellorRecord:
    """Create a counsellor profile for an existing staff account (seed.py / admin)."""
    if not display_name.strip():
        raise ValueError("display name is required")
    row = Counsellor(account_id=account_id, display_name=display_name.strip(),
                     specialties=",".join(s.strip() for s in specialties if s.strip()))
    db.add(row)
    db.commit()
    rec = _record(row)
    with _lock:
        _counsellors.put(rec.id, rec)
        _by_account.put(rec.account_id, rec.id)
        _open.put(rec.id, IntervalTree())
        _busy.put(rec.id, IntervalTree())
    return rec


def counsellors() -> list[CounsellorRecord]:
    with _lock:
        recs = _counsellors.values()
    return sorted(recs, key=lambda r: (r.display_name.lower(), r.id))


def get_counsellor(counsellor_id: int) -> CounsellorRecord:
    with _lock:
        rec = _counsellors.get(counsellor_id)
    if rec is None:
        raise CounsellorNotFound(counsellor_id)
    return rec


def counsellor_for_account(account_id: int) -> CounsellorRecord:
    """The counsellor profile of a logged-in counsellor. CounsellorNotFound if they have none."""
    with _lock:
        cid = _by_account.get(account_id)
    if cid is None:
        raise CounsellorNotFound(account_id)
    return get_counsellor(cid)


def to_counsellor_dict(rec: CounsellorRecord) -> dict:
    return {"id": rec.id, "display_name": rec.display_name, "specialties": list(rec.specialties)}


# --- free time: tree query + one sweep ------------------------------------------------------------------

def _free_between(counsellor_id: int, lo: int, hi: int, need: int, limit: int | None = None):
    """Open windows, busy parts and free start times inside [lo, hi) (epoch seconds).

    Each window comes from an interval-tree query on _open; the busy intervals overlapping it come
    from a query on _busy, already sorted by start (in-order walk pruned with max), so one sweep
    finds the gaps: O(log n + k). A start is offered when a whole session (`need` seconds) fits.
    """
    with _lock:
        windows = list(_open.get(counsellor_id).query(lo, hi - 1)) if hi > lo else []
        spans = []
        for ws, we_closed in windows:
            ws, we = max(ws, lo), min(we_closed + 1, hi)
            spans.append((ws, we, list(_busy.get(counsellor_id).query(ws, we - 1))))
    now = _ts(clock.now())
    open_out, busy_out, starts = [], [], []
    for ws, we, busy in spans:
        open_out.append((ws, we))
        cursor = ws
        for bs, be_closed in busy:
            be = be_closed + 1
            busy_out.append((max(bs, ws), min(be, we)))
            _fill(starts, cursor, bs, need, now)
            cursor = max(cursor, be)
        _fill(starts, cursor, we, need, now)
        if limit is not None and len(starts) >= limit:
            break
    return open_out, busy_out, starts


def _fill(out: list, gap_start: int, gap_end: int, need: int, now: int) -> None:
    """Every quarter-hour start t in the gap with t > now and t + need <= gap_end."""
    t = max(gap_start, now + 1)
    if t % GRID_SECONDS != 0:                  # round up to the next quarter hour
        t += GRID_SECONDS - t % GRID_SECONDS
    while t + need <= gap_end:
        out.append(t)
        t += GRID_SECONDS


def free_day(counsellor_id: int, day: date, first_visit: bool = False) -> dict:
    """The booking grid for one Dubai-time day: open windows, busy time (no detail) and free starts."""
    get_counsellor(counsellor_id)
    length = FIRST_VISIT if first_visit else SESSION
    lo = datetime.combine(day, time(0), tzinfo=clock.DUBAI)
    open_, busy, starts = _free_between(counsellor_id, _ts(lo), _ts(lo + timedelta(days=1)),
                                        int(length.total_seconds()))
    return {"counsellor_id": counsellor_id, "day": day, "session_minutes": int(length.total_seconds() // 60),
            "open": [{"start": _dt(s), "end": _dt(e)} for s, e in open_],
            "busy": [{"start": _dt(s), "end": _dt(e)} for s, e in busy],
            "starts": [_dt(t) for t in starts]}


def has_free_time(counsellor_id: int, within: timedelta) -> bool:
    """Is there any bookable 45-minute session from now until now + within?"""
    now = clock.now()
    _, _, starts = _free_between(counsellor_id, _ts(now), _ts(now + within), int(SESSION.total_seconds()), limit=1)
    return bool(starts)


# --- booking ------------------------------------------------------------------------------------------

def _check_new_session(start: datetime, reason: str) -> None:
    if reason not in REASONS:
        raise ValueError(f"reason must be one of: {', '.join(REASONS)}")
    if start.second or start.microsecond or _ts(start) % GRID_SECONDS:
        raise ValueError("sessions start on a quarter hour (:00, :15, :30, :45)")
    now = clock.now()
    if start <= now:
        raise ValueError("that time has already passed")
    if start > now + MAX_AHEAD:
        raise ValueError(f"sessions can be booked at most {MAX_AHEAD.days} days ahead")


def _inside_window(counsellor_id: int, s: int, e: int) -> bool:
    """[s, e) lies inside one open window. Windows never overlap, so the one the tree finds is the only one."""
    hit = _open.get(counsellor_id).find_overlap(s, e - 1)
    return hit is not None and hit[0] <= s and e - 1 <= hit[1]


def _check_student_free(db: Session, pseudonym: str, start: datetime, end: datetime) -> None:
    clash = db.scalar(select(Booking.id).where(Booking.pseudonym == pseudonym, Booking.status == "active",
                                               Booking.start < end, Booking.end > start).limit(1))
    if clash is not None:
        raise SlotTaken("you already have a session at that time")


def _begin_immediate(db: Session) -> None:
    """Take SQLite's write lock now, so the SQL re-check and the INSERT after it are one atomic step."""
    if db.get_bind().dialect.name != "sqlite":
        return
    conn = db.connection()
    if not conn.connection.dbapi_connection.in_transaction:
        conn.exec_driver_sql("BEGIN IMMEDIATE")


def _sql_overlap(db: Session, counsellor_id: int, start: datetime, end: datetime,
                 except_offer: int | None = None) -> bool:
    """Safety net behind the tree: does the database hold anything busy in [start, end)?"""
    if db.scalar(select(Booking.id).where(Booking.counsellor_id == counsellor_id, Booking.status == "active",
                                          Booking.start < end, Booking.end > start).limit(1)) is not None:
        return True
    if db.scalar(select(Availability.id).where(Availability.counsellor_id == counsellor_id,
                                               Availability.kind == "blocked", Availability.start < end,
                                               Availability.end > start).limit(1)) is not None:
        return True
    q = select(Offer.id).where(Offer.counsellor_id == counsellor_id, Offer.status == "open",
                               Offer.start < end, Offer.end > start)
    if except_offer is not None:
        q = q.where(Offer.id != except_offer)
    return db.scalar(q.limit(1)) is not None


def _insert_booking(db: Session, counsellor_id: int, pseudonym: str, start: datetime, end: datetime, reason: str,
                    first_visit: bool, reveal: bool, identity_blob: str | None, except_offer: int | None = None,
                    before_commit: Callable[[Booking], None] | None = None) -> Booking:
    """BEGIN IMMEDIATE, re-check, INSERT, COMMIT, then the tree. Call inside lock_for(counsellor_id)."""
    _begin_immediate(db)
    if _sql_overlap(db, counsellor_id, start, end, except_offer):
        db.rollback()
        raise SlotTaken("someone just took this slot")
    row = Booking(counsellor_id=counsellor_id, pseudonym=pseudonym, start=start, end=end, reason=reason,
                  first_visit=first_visit, status="active", revealed=reveal,
                  enc_identity=identity_blob if reveal else None, created_at=clock.now())
    db.add(row)
    db.flush()
    if before_commit is not None:
        before_commit(row)
    db.commit()
    # A hold for the same time has the same key, so this replaces it.
    _tree_add(db, counsellor_id, "busy", _ts(start), _ts(end), ("booking", row.id))
    return row


def _after_booking(db: Session, rec: CounsellorRecord, row: Booking) -> None:
    notify.schedule_session_reminders(db, row.id, row.pseudonym, row.start)
    notify.send_now(db, notify.staff_recipient(rec.account_id), "session_booked",
                    {"title": "New session booked",
                     "body": f"{tag(row.pseudonym)} booked {_when(row.start)} ({row.reason.replace('_', ' ')}).",
                     "booking_id": row.id})
    notify.publish(notify.BROADCAST, "slot_taken",
                   {"counsellor_id": rec.id, "start": row.start, "end": row.end})


def book(db: Session, pseudonym: str, counsellor_id: int, start: datetime, reason: str,
         first_visit: bool = False, reveal: bool = False, identity_blob: str | None = None) -> Booking:
    """Book a 45-minute session (60 for a first visit) starting on a quarter hour inside an open window.

    identity_blob is the student's encrypted name and email, stored only when reveal is ticked.
    """
    rec = get_counsellor(counsellor_id)
    start = _utc(start)
    end = start + (FIRST_VISIT if first_visit else SESSION)
    _check_new_session(start, reason)
    s, e = _ts(start), _ts(end)
    with lock_for(rec.id):
        with _lock:
            inside = _inside_window(rec.id, s, e)
            clash = _busy.get(rec.id).find_overlap(s, e - 1)
        if not inside:
            raise ValueError("that time is outside the counsellor's hours")
        if clash is not None:
            raise SlotTaken("someone just took this slot")
        _check_student_free(db, pseudonym, start, end)
        row = _insert_booking(db, rec.id, pseudonym, start, end, reason, first_visit, reveal, identity_blob)
    _after_booking(db, rec, row)
    return row


# --- holds for waitlist offers (used by services/waitlist.py, inside lock_for) ------------------------------

def hold(db: Session, counsellor_id: int, start: datetime, end: datetime, offer_id: int) -> None:
    """Keep [start, end) busy while it is offered to someone; re-holding the same time moves it to a new offer."""
    _tree_add(db, counsellor_id, "busy", _ts(start), _ts(end), ("hold", offer_id))
    notify.publish(notify.BROADCAST, "slot_taken", {"counsellor_id": counsellor_id, "start": start, "end": end})


def release(db: Session, counsellor_id: int, start: datetime, end: datetime) -> None:
    """Nobody on the waitlist took the time: show it to everyone."""
    _tree_remove(db, counsellor_id, "busy", _ts(start), _ts(end))
    notify.publish(notify.BROADCAST, "slot_freed", {"counsellor_id": counsellor_id, "start": start, "end": end})


def book_from_offer(db: Session, offer: Offer, pseudonym: str, reason: str, reveal: bool = False,
                    identity_blob: str | None = None,
                    before_commit: Callable[[Booking], None] | None = None) -> Booking:
    """Turn an offer's hold into a booking; before_commit closes the offer in the same transaction."""
    if reason not in REASONS:
        raise ValueError(f"reason must be one of: {', '.join(REASONS)}")
    rec = get_counsellor(offer.counsellor_id)
    with lock_for(rec.id):
        _check_student_free(db, pseudonym, offer.start, offer.end)
        row = _insert_booking(db, rec.id, pseudonym, offer.start, offer.end, reason,
                              offer.end - offer.start >= FIRST_VISIT, reveal, identity_blob,
                              except_offer=offer.id, before_commit=before_commit)
    _after_booking(db, rec, row)
    return row


# --- cancel / mark ----------------------------------------------------------------------------------------

def _own_booking(db: Session, booking_id: int, pseudonym: str | None, counsellor_id: int | None) -> Booking:
    """The booking if it belongs to this student or counsellor; otherwise 404 (never confirm it exists)."""
    row = db.get(Booking, booking_id)
    if (row is None or (pseudonym is not None and row.pseudonym != pseudonym)
            or (counsellor_id is not None and row.counsellor_id != counsellor_id)):
        raise BookingNotFound(booking_id)
    return row


def cancel(db: Session, booking_id: int, *, pseudonym: str | None = None,
           counsellor_id: int | None = None) -> Booking:
    """Cancel by the student (pseudonym) or the counsellor (counsellor_id). The freed time goes to the
    waitlist first; only if nobody is waiting is it shown as free."""
    from app.services import waitlist  # imports booking too

    if (pseudonym is None) == (counsellor_id is None):
        raise ValueError("cancel needs exactly one of pseudonym or counsellor_id")
    row = _own_booking(db, booking_id, pseudonym, counsellor_id)
    if row.status != "active":
        raise ValueError(f"this session is already {row.status.replace('_', ' ')}")
    if row.start <= clock.now():
        raise ValueError("this session has already started")
    rec = get_counsellor(row.counsellor_id)
    with lock_for(rec.id):
        row.status = "cancelled"
        row.cancelled_by = "student" if pseudonym is not None else "counsellor"
        db.commit()
        _tree_remove(db, rec.id, "busy", _ts(row.start), _ts(row.end))
        notify.cancel_session_reminders(db, row.id)
        offered = waitlist.offer_freed(db, rec.id, row.start, row.end)

    if pseudonym is not None:
        notify.send_now(db, notify.staff_recipient(rec.account_id), "session_cancelled",
                        {"title": "Session cancelled",
                         "body": f"{tag(row.pseudonym)} cancelled {_when(row.start)}.", "booking_id": row.id})
    else:
        notify.send_now(db, row.pseudonym, "session_cancelled",
                        {"title": "Your session was cancelled",
                         "body": f"{rec.display_name} cancelled your session on {_when(row.start)}. "
                                 "Please book another time.", "booking_id": row.id})
    if not offered:
        notify.publish(notify.BROADCAST, "slot_freed", {"counsellor_id": rec.id, "start": row.start, "end": row.end})
    return row


def mark(db: Session, counsellor_id: int, booking_id: int, status: str) -> Booking:
    """Counsellor marks a session that has started as completed or no_show."""
    if status not in ("completed", "no_show"):
        raise ValueError("status must be completed or no_show")
    row = _own_booking(db, booking_id, None, counsellor_id)
    if row.status not in ("active", "completed", "no_show"):
        raise ValueError(f"this session is {row.status}")
    if row.start > clock.now():
        raise ValueError("this session hasn't started yet")
    row.status = status
    db.commit()
    return row


# --- availability (counsellors) -------------------------------------------------------------------------

def add_availability(db: Session, counsellor_id: int, start: datetime, end: datetime, kind: str = "open",
                     note: str = "") -> Availability:
    """An open window (may not overlap another window) or blocked time (may not overlap anything busy)."""
    rec = get_counsellor(counsellor_id)
    if kind not in ("open", "blocked"):
        raise ValueError("kind must be open or blocked")
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise ValueError("end must be after start")
    if end - start > MAX_WINDOW:
        raise ValueError("a window can be at most 24 hours long")
    if end <= clock.now():
        raise ValueError("that time has already passed")
    s, e = _ts(start), _ts(end)
    with lock_for(rec.id):
        which = "open" if kind == "open" else "busy"
        with _lock:
            clash = _tree(which, rec.id).find_overlap(s, e - 1)
        if clash is not None:
            raise SlotTaken("that overlaps another open window" if kind == "open"
                            else "that overlaps a session or other blocked time")
        row = Availability(counsellor_id=rec.id, start=start, end=end, kind=kind, note=note.strip())
        db.add(row)
        db.commit()
        value = row.id if kind == "open" else ("blocked", row.id)
        _tree_add(db, rec.id, which, s, e, value)
    event = "slot_freed" if kind == "open" else "slot_taken"
    notify.publish(notify.BROADCAST, event, {"counsellor_id": rec.id, "start": start, "end": end})
    return row


def remove_availability(db: Session, counsellor_id: int, availability_id: int) -> None:
    """Delete a window or a block. A window that still has sessions (or holds) inside cannot go."""
    row = db.get(Availability, availability_id)
    if row is None or row.counsellor_id != counsellor_id:
        raise AvailabilityNotFound(availability_id)
    s, e = _ts(row.start), _ts(row.end)
    kind = row.kind
    with lock_for(counsellor_id):
        if kind == "open":
            # every busy interval inside the window; a session or an offer hold means it can't go
            with _lock:
                busy = _busy.get(counsellor_id)
                for key in busy.query(s, e - 1):
                    if busy.search(key)[0] in ("booking", "hold"):
                        raise SlotTaken("this window still has sessions; cancel them first")
        db.delete(row)
        db.commit()
        _tree_remove(db, counsellor_id, "open" if kind == "open" else "busy", s, e)
    event = "slot_taken" if kind == "open" else "slot_freed"
    notify.publish(notify.BROADCAST, event, {"counsellor_id": counsellor_id, "start": row.start, "end": row.end})


def list_availability(db: Session, counsellor_id: int, lo: datetime, hi: datetime) -> list[Availability]:
    if hi < lo:
        raise ValueError("'to' must not be before 'from'")
    return list(db.scalars(select(Availability).where(Availability.counsellor_id == counsellor_id,
                                                      Availability.end > lo, Availability.start < hi)
                           .order_by(Availability.start)))


def to_availability_dict(row: Availability) -> dict:
    return {"id": row.id, "start": row.start, "end": row.end, "kind": row.kind, "note": row.note}


# --- views ------------------------------------------------------------------------------------------------

def my_bookings(db: Session, pseudonym: str) -> list[Booking]:
    return list(db.scalars(select(Booking).where(Booking.pseudonym == pseudonym).order_by(Booking.start)))


def sessions_on(db: Session, counsellor_id: int, day: date) -> list[Booking]:
    """The counsellor's sessions starting on this Dubai-time day (cancelled ones left out)."""
    lo = datetime.combine(day, time(0), tzinfo=clock.DUBAI)
    return list(db.scalars(select(Booking).where(Booking.counsellor_id == counsellor_id,
                                                 Booking.start >= lo, Booking.start < lo + timedelta(days=1),
                                                 Booking.status != "cancelled").order_by(Booking.start)))


def to_dict(row: Booking) -> dict:
    """Student view of their own booking."""
    with _lock:
        rec = _counsellors.get(row.counsellor_id)
    return {"id": row.id, "counsellor_id": row.counsellor_id,
            "counsellor_name": rec.display_name if rec is not None else "", "start": row.start, "end": row.end,
            "reason": row.reason, "first_visit": row.first_visit, "status": row.status, "revealed": row.revealed}


def to_session_dict(row: Booking, identity: str | None = None) -> dict:
    """Counsellor view: a pseudonym tag and a reason category; a name only if the student opted in."""
    return {"id": row.id, "start": row.start, "end": row.end, "student": tag(row.pseudonym), "reason": row.reason,
            "first_visit": row.first_visit, "status": row.status, "revealed": row.revealed,
            "identity": identity if row.revealed else None}
