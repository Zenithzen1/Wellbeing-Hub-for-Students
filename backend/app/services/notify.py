"""Notifications: timed min-heap -> FIFO delivery queue, inbox, SSE fan-out. Owner: Divyam.

Plan section 7. Two structures, two jobs:

* The timed heap (our IndexedMinHeap, keyed by (send_at, heap id)) answers "what is due next?".
  Heap ids are "n:<notification id>" for messages and "job:<kind>:<ref>" for internal jobs
  (offer expiry, waitlist ageing) that the scheduler runs itself instead of delivering.
* The delivery queue (our Queue) holds notification ids that are already due, first in first out.

Every message is first a `notifications` row (status pending), then a heap entry (write-through).
Delivery: external channels (email stub) -> row marked sent -> SSE push to open tabs. A failing
channel retries after 1, 5 and 25 minutes; the 4th failure moves the row to the dead-letter list.

For other services:
    schedule(db, recipient, kind, payload, send_at, ref)   any message, at any time
    send_now(db, recipient, kind, payload, ref)            the same, due immediately
    cancel(db, ref)                                        drop pending messages created by ref
    schedule_session_reminders(db, booking_id, recipient, start) / cancel_session_reminders(db, booking_id)
    register_job(kind, handler); schedule_job(kind, ref, at); cancel_job(kind, ref)
        handler(db, ref) runs on the scheduler tick once `at` has passed. Jobs are not stored:
        the owning service re-schedules them from its own tables in its rebuild().
    publish(channel, event, data)                          SSE push, e.g. publish("all", "slot_taken", {...})
"""

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.deps import CurrentUser
from app.ds import HashMap, IndexedMinHeap, Queue
from app.models import Notification, NotificationRead

log = logging.getLogger(__name__)

BROADCAST = "all"  # recipient / SSE channel that every logged-in tab listens to
BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=25))
MAX_ATTEMPTS = len(BACKOFF) + 1  # 4th failure -> dead-letter list
LATE_LIMIT = timedelta(hours=1)  # missed while the server was off: send if less late than this, else skip
SESSION_REMINDERS = ((timedelta(hours=24), "Session in 24 hours"), (timedelta(hours=1), "Session in 1 hour"))
REMINDER_KINDS = ("session_reminder", "event_reminder")

# All structure access goes through this lock: routes, the scheduler tick and other services may
# run on different threads.
_lock = threading.RLock()
_heap = IndexedMinHeap()  # heap id -> (send_at, heap id)
_queue = Queue()          # notification ids that are due, in delivery order
_jobs = HashMap()         # "job:<kind>:<ref>" -> (kind, ref)
_handlers = HashMap()     # job kind -> handler(db, ref); registered at import time, survive reset()


# --- recipients -----------------------------------------------------------------------------

def staff_recipient(account_id: int) -> str:
    return f"acct:{account_id}"


def recipient_for(user: CurrentUser) -> str:
    """Students are addressed by pseudonym, staff by account id."""
    if user.role == "S":
        if not user.pseudonym:
            raise ValueError("student without a pseudonym")
        return user.pseudonym
    return staff_recipient(user.account_id)


# --- startup ----------------------------------------------------------------------------------

def reset() -> None:
    """Empty the heap, queue and jobs. Called first thing in rebuild_all(), before any service
    re-schedules its jobs."""
    global _heap, _queue, _jobs
    with _lock:
        _heap, _queue, _jobs = IndexedMinHeap(), Queue(), HashMap()


def rebuild(db: Session) -> None:
    """Load pending rows into the timed heap. A row whose time passed while the server was off is
    sent at the next tick if it is less than an hour late; otherwise it is marked skipped."""
    cutoff = clock.now() - LATE_LIMIT
    rows = db.scalars(select(Notification).where(Notification.status == "pending")).all()
    for row in rows:
        if row.send_at < cutoff:
            row.status = "skipped"
    db.commit()
    with _lock:
        for row in rows:
            if row.status == "pending" and not _heap.contains(_hid(row.id)):
                _heap.push(_hid(row.id), (row.send_at, _hid(row.id)))


# --- scheduling ---------------------------------------------------------------------------------

def _hid(notification_id: int) -> str:
    return f"n:{notification_id}"


def schedule(db: Session, recipient: str, kind: str, payload: dict, send_at: datetime,
             ref: str | None = None) -> Notification:
    """Store a pending message (DB commit first) and put it in the timed heap. payload should carry
    at least "title" and "body"."""
    row = Notification(recipient=recipient, kind=kind, payload=json.dumps(payload), send_at=send_at,
                       status="pending", attempts=0, ref=ref)
    db.add(row)
    db.commit()
    with _lock:
        _heap.push(_hid(row.id), (row.send_at, _hid(row.id)))
    return row


def send_now(db: Session, recipient: str, kind: str, payload: dict, ref: str | None = None) -> Notification:
    """Due immediately: delivered on the next scheduler tick (within 15 s)."""
    return schedule(db, recipient, kind, payload, clock.now(), ref)


def cancel(db: Session, ref: str) -> int:
    """Cancel every pending message created by `ref` (e.g. "booking:12"). Returns how many. O(m log n)"""
    rows = db.scalars(select(Notification).where(Notification.ref == ref, Notification.status == "pending")).all()
    for row in rows:
        row.status = "cancelled"
    db.commit()
    with _lock:
        for row in rows:
            if _heap.contains(_hid(row.id)):
                _heap.remove(_hid(row.id))
            # an id already in the delivery queue is skipped there, because its row is no longer pending
    return len(rows)


def schedule_session_reminders(db: Session, booking_id: int, recipient: str, start: datetime) -> list[Notification]:
    """The T-24h and T-1h reminders for a booking (ref "booking:<id>"); times already past are skipped."""
    now = clock.now()
    when = clock.to_local(start).strftime("%a %d %b, %H:%M")
    rows = []
    for before, title in SESSION_REMINDERS:
        if start - before > now:
            payload = {"title": title, "body": f"Your counselling session starts {when}.", "booking_id": booking_id}
            rows.append(schedule(db, recipient, "session_reminder", payload, start - before, f"booking:{booking_id}"))
    return rows


def cancel_session_reminders(db: Session, booking_id: int) -> int:
    return cancel(db, f"booking:{booking_id}")


def register_job(kind: str, handler) -> None:
    """handler(db, ref) is called on the scheduler tick when a job of this kind falls due."""
    with _lock:
        _handlers.put(kind, handler)


def schedule_job(kind: str, ref: str, at: datetime) -> None:
    """Run the `kind` handler for `ref` at time `at`; re-scheduling the same (kind, ref) moves it."""
    hid = f"job:{kind}:{ref}"
    with _lock:
        _jobs.put(hid, (kind, ref))
        if _heap.contains(hid):
            _heap.update(hid, (at, hid))
        else:
            _heap.push(hid, (at, hid))


def cancel_job(kind: str, ref: str) -> bool:
    hid = f"job:{kind}:{ref}"
    with _lock:
        if not _heap.contains(hid):
            return False
        _heap.remove(hid)
        _jobs.remove(hid)
        return True


def pending_count() -> int:
    """Entries waiting in the timed heap (messages and jobs)."""
    return len(_heap)


# --- the tick --------------------------------------------------------------------------------------

def _email_stub(row: Notification) -> None:
    """Stand-in for institute email (plan section 14). Replace or monkeypatch in tests."""
    log.info("email (stub) to %s: %s", row.recipient, json.loads(row.payload).get("title", row.kind))


CHANNELS = [_email_stub]  # external channels; a raise counts as a failed delivery


def tick(db: Session) -> None:
    """One scheduler pass: pop everything due from the timed heap, run due jobs, deliver the queue."""
    now = clock.now()
    due_jobs = []
    with _lock:
        while len(_heap) and _heap.peek()[1][0] <= now:
            hid, _ = _heap.pop()
            if hid.startswith("job:"):
                due_jobs.append(_jobs.remove(hid))
            else:
                _queue.enqueue(int(hid[2:]))
    for kind, ref in due_jobs:
        handler = _handlers.get(kind)
        if handler is None:
            log.error("no handler registered for job kind %r (ref %r)", kind, ref)
            continue
        try:
            handler(db, ref)
        except Exception:  # one bad job must not stop the others
            db.rollback()
            log.exception("job %s:%s failed", kind, ref)
    dispatch(db)


def dispatch(db: Session) -> None:
    """Deliver everything in the queue, first in first out."""
    while True:
        with _lock:
            if _queue.is_empty():
                return
            nid = _queue.dequeue()
        row = db.get(Notification, nid)
        if row is None or row.status != "pending":
            continue
        try:
            for channel in CHANNELS:
                channel(row)
        except Exception as exc:
            _failed(db, row, exc)
            continue
        row.status = "sent"  # only after the channels succeeded (at-least-once)
        db.commit()
        publish(row.recipient, _sse_event(row.kind), to_dict(row))


def _failed(db: Session, row: Notification, exc: Exception) -> None:
    row.attempts += 1
    row.last_error = repr(exc)[:500]
    if row.attempts >= MAX_ATTEMPTS:
        row.status = "dead"
        db.commit()
        log.warning("notification %s moved to the dead-letter list: %s", row.id, row.last_error)
        return
    row.send_at = clock.now() + BACKOFF[row.attempts - 1]
    db.commit()
    with _lock:
        _heap.push(_hid(row.id), (row.send_at, _hid(row.id)))


def _sse_event(kind: str) -> str:
    return "reminder" if kind in REMINDER_KINDS else "notification"


# --- inbox and admin views ----------------------------------------------------------------------------

def to_dict(row: Notification, read: bool = False) -> dict:
    payload = json.loads(row.payload or "{}")
    return {"id": row.id, "kind": row.kind, "title": payload.get("title", ""), "body": payload.get("body", ""),
            "payload": payload, "send_at": row.send_at, "read": read}


def inbox(db: Session, recipient: str, limit: int = 50) -> list[dict]:
    """Delivered messages for this recipient (including announcements), newest first."""
    rows = db.scalars(
        select(Notification)
        .where(Notification.recipient.in_((recipient, BROADCAST)), Notification.status == "sent")
        .order_by(Notification.send_at.desc(), Notification.id.desc())
        .limit(limit)
    ).all()
    read = HashMap()
    ids = [row.id for row in rows]
    if ids:
        for nid in db.scalars(select(NotificationRead.notification_id).where(
                NotificationRead.recipient == recipient, NotificationRead.notification_id.in_(ids))):
            read.put(nid, True)
    return [to_dict(row, read.contains(row.id)) for row in rows]


def mark_read(db: Session, recipient: str, notification_id: int) -> None:
    """KeyError unless the message was delivered to this recipient (or to everyone)."""
    row = db.get(Notification, notification_id)
    if row is None or row.status != "sent" or row.recipient not in (recipient, BROADCAST):
        raise KeyError(notification_id)
    if db.get(NotificationRead, (notification_id, recipient)) is None:
        db.add(NotificationRead(notification_id=notification_id, recipient=recipient))
        db.commit()


def announce(db: Session, title: str, body: str, send_at: datetime | None = None) -> Notification:
    """Admin announcement to everyone, now or at a chosen time."""
    return schedule(db, BROADCAST, "announcement", {"title": title, "body": body}, send_at or clock.now())


def dead_letters(db: Session, limit: int = 100) -> list[dict]:
    """Messages that failed 4 times. The recipient is left out on purpose (admins never see pseudonyms)."""
    rows = db.scalars(select(Notification).where(Notification.status == "dead")
                      .order_by(Notification.send_at.desc()).limit(limit)).all()
    return [{"id": row.id, "kind": row.kind, "title": json.loads(row.payload or "{}").get("title", ""),
             "attempts": row.attempts, "last_attempt_at": row.send_at, "last_error": row.last_error}
            for row in rows]


# --- Server-Sent Events fan-out ------------------------------------------------------------------------

@dataclass(eq=False)
class Subscriber:
    """One open /stream connection, listening on a few channels (its recipient id and "all")."""

    channels: tuple[str, ...]
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue


_subscribers = HashMap()  # channel -> HashMap(id(subscriber) -> Subscriber)


def subscribe(channels: tuple[str, ...]) -> Subscriber:
    """Call from inside the event loop (the /stream route)."""
    sub = Subscriber(channels, asyncio.get_running_loop(), asyncio.Queue(maxsize=100))
    with _lock:
        for ch in channels:
            if not _subscribers.contains(ch):
                _subscribers.put(ch, HashMap())
            _subscribers.get(ch).put(id(sub), sub)
    return sub


def unsubscribe(sub: Subscriber) -> None:
    with _lock:
        for ch in sub.channels:
            subs = _subscribers.get(ch)
            if subs is not None and subs.contains(id(sub)):
                subs.remove(id(sub))
                if len(subs) == 0:
                    _subscribers.remove(ch)


def _offer(queue: asyncio.Queue, message) -> None:
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:  # a stuck tab must not grow memory forever; it refetches on reconnect
        pass


def publish(channel: str, event: str, data: dict) -> None:
    """Push one SSE message to every tab listening on `channel`. Safe to call from any thread."""
    with _lock:
        subs = _subscribers.get(channel)
        targets = subs.values() if subs is not None else []
    for sub in targets:
        try:
            sub.loop.call_soon_threadsafe(_offer, sub.queue, (event, data))
        except RuntimeError:  # that tab's loop is closed
            unsubscribe(sub)


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=_json_default)}\n\n"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")
