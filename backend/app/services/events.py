"""Events: AVL tree by start time, range / next-k queries, registration FIFO queue. Owner: Divyam.

Plan section 6.
* The events tree is our AVLTree keyed (start, event id); the id breaks ties between events that
  start at the same moment. Values are small EventRecords; the full rows stay in SQLite.
  Editing an event's time is delete(old key) then insert(new key). Past events stay in the tree.
* Each full event has a FIFO Queue of waitlisted students. A student who leaves the waitlist is
  dropped lazily: the queue holds (pseudonym, position) and an entry only counts while
  _waiting[(event id, pseudonym)] still equals its position, so a re-join can't reuse an old place.
* Every registration schedules a "starts in 1 hour" reminder (ref "event:<id>:<pseudonym>").

Write-through: every change commits to the database first, then updates the structures.
Errors: EventNotFound (-> 404), RegistrationConflict (-> 409), ValueError (-> 400).
"""

import logging
import math
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import clock
from app.ds import AVLTree, HashMap, Queue
from app.models import Event, ItemTag, Registration, Tag
from app.services import notify

REMINDER_BEFORE = timedelta(hours=1)

log = logging.getLogger(__name__)


class EventNotFound(KeyError):
    pass


class RegistrationConflict(Exception):
    pass


@dataclass
class EventRecord:
    id: int
    title: str
    start: datetime
    end: datetime
    location: str
    capacity: int
    tags: tuple[str, ...]
    registered: int = 0
    waitlisted: int = 0

    @property
    def key(self) -> tuple:
        return (self.start, self.id)


_lock = threading.RLock()
_tree = AVLTree()     # (start, event id) -> EventRecord
_records = HashMap()  # event id -> EventRecord (finds the tree key from an id)
_queues = HashMap()   # event id -> Queue of (pseudonym, position)
_waiting = HashMap()  # (event id, pseudonym) -> position of the live queue entry
_next_position = 1    # global, increasing: orders waitlisted registrations
_listeners = []       # fn(event_id, tags or None), called after a create / update / remove commits


def on_change(fn) -> None:
    """Call fn(event_id, tags) after an event is created or edited and fn(event_id, None) after it is
    deleted. The recommendations graph uses this to keep its workshop nodes in step."""
    _listeners.append(fn)


def _changed(event_id: int, tags: tuple[str, ...] | None) -> None:
    for fn in _listeners:
        try:
            fn(event_id, tags)
        except Exception:  # a listener must never break the event write, which is already committed
            log.exception("event change listener failed for event %s", event_id)


# --- startup ----------------------------------------------------------------------------------

def rebuild(db: Session) -> None:
    """Rebuild the tree, the counts and the event queues from SQLite."""
    global _tree, _records, _queues, _waiting, _next_position
    tree, records, queues, waiting = AVLTree(), HashMap(), HashMap(), HashMap()

    tags = HashMap()  # event id -> list of tag names
    for item, name in db.execute(select(ItemTag.item, Tag.name).join(Tag, Tag.id == ItemTag.tag_id)
                                 .where(ItemTag.item.like("e:%")).order_by(Tag.name)):
        eid = int(item[2:])
        if not tags.contains(eid):
            tags.put(eid, [])
        tags.get(eid).append(name)

    for row in db.scalars(select(Event)):
        rec = EventRecord(row.id, row.title, row.start, row.end, row.location, row.capacity,
                          tuple(tags.get(row.id, [])))
        records.put(rec.id, rec)
        tree.insert(rec.key, rec)

    for reg in db.scalars(select(Registration).where(Registration.status.in_(("registered", "waitlisted")))
                          .order_by(Registration.position)):
        rec = records.get(reg.event_id)
        if rec is None:
            continue
        if reg.status == "registered":
            rec.registered += 1
        else:
            rec.waitlisted += 1
            if not queues.contains(rec.id):
                queues.put(rec.id, Queue())
            queues.get(rec.id).enqueue((reg.pseudonym, reg.position))
            waiting.put((rec.id, reg.pseudonym), reg.position)

    top = db.scalar(select(func.max(Registration.position))) or 0
    with _lock:
        _tree, _records, _queues, _waiting, _next_position = tree, records, queues, waiting, top + 1


# --- queries --------------------------------------------------------------------------------------

def get(event_id: int) -> EventRecord:
    with _lock:
        rec = _records.get(event_id)
    if rec is None:
        raise EventNotFound(event_id)
    return rec


def between(lo: datetime, hi: datetime, tag: str | None = None) -> list[EventRecord]:
    """Events starting in [lo, hi], in start order (AVL range query, O(log n + k))."""
    if hi < lo:
        raise ValueError("'to' must not be before 'from'")
    with _lock:
        found = _tree.range((lo, -math.inf), (hi, math.inf))
    tag = _norm_tag(tag) if tag else None
    return [rec for _, rec in found if tag is None or tag in rec.tags]


def upcoming(k: int = 5) -> list[EventRecord]:
    """The next k events starting from now (AVL next_k, O(log n + k))."""
    with _lock:
        found = _tree.next_k((clock.now(), -math.inf), k)
    return [rec for _, rec in found]


def statuses_for(db: Session, pseudonym: str, event_ids: list[int]) -> HashMap:
    """event id -> "registered" | "waitlisted" for this student, among event_ids."""
    out = HashMap()
    if event_ids:
        for eid, status in db.execute(select(Registration.event_id, Registration.status).where(
                Registration.pseudonym == pseudonym, Registration.event_id.in_(event_ids),
                Registration.status.in_(("registered", "waitlisted")))):
            out.put(eid, status)
    return out


def to_dict(rec: EventRecord, my_status: str | None = None) -> dict:
    return {"id": rec.id, "title": rec.title, "start": rec.start, "end": rec.end, "location": rec.location,
            "capacity": rec.capacity, "tags": list(rec.tags), "registered": rec.registered,
            "waitlisted": rec.waitlisted, "spots_left": max(0, rec.capacity - rec.registered),
            "my_status": my_status}


# --- admin: create / edit / delete ----------------------------------------------------------------

def _norm_tag(name: str) -> str:
    return name.strip().lower()


def _set_tags(db: Session, event_id: int, names: list[str]) -> tuple[str, ...]:
    """Replace the event's item_tags rows (item "e:<id>"); unknown tag names are added to tags."""
    clean = sorted({_norm_tag(n) for n in names if n.strip()})
    if any(len(n) > 50 for n in clean):
        raise ValueError("tag names are at most 50 characters")
    item = f"e:{event_id}"
    db.execute(delete(ItemTag).where(ItemTag.item == item))
    for name in clean:
        tag = db.scalar(select(Tag).where(Tag.name == name))
        if tag is None:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        db.add(ItemTag(item=item, tag_id=tag.id))
    return tuple(clean)


def _validate(title: str, start: datetime, end: datetime, capacity: int) -> None:
    if not title.strip():
        raise ValueError("title is required")
    if end <= start:
        raise ValueError("end must be after start")
    if capacity < 1:
        raise ValueError("capacity must be at least 1")


def create(db: Session, title: str, start: datetime, end: datetime, location: str = "",
           capacity: int = 20, tags: list[str] | None = None) -> EventRecord:
    start, end = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
    _validate(title, start, end, capacity)
    row = Event(title=title.strip(), start=start, end=end, location=location.strip(), capacity=capacity)
    db.add(row)
    db.flush()
    names = _set_tags(db, row.id, tags or [])
    db.commit()
    rec = EventRecord(row.id, row.title, start, end, row.location, capacity, names)
    with _lock:
        _records.put(rec.id, rec)
        _tree.insert(rec.key, rec)
    _changed(rec.id, names)
    return rec


def update(db: Session, event_id: int, title: str | None = None, start: datetime | None = None,
           end: datetime | None = None, location: str | None = None, capacity: int | None = None,
           tags: list[str] | None = None) -> EventRecord:
    """Change any fields. A new start time moves the event in the tree and re-times its reminders;
    a bigger capacity moves people in from the waitlist. A smaller one never removes anyone."""
    rec = get(event_id)
    row = db.get(Event, event_id)
    if row is None:
        raise EventNotFound(event_id)
    new_start = start.astimezone(timezone.utc) if start is not None else rec.start
    new_end = end.astimezone(timezone.utc) if end is not None else rec.end
    new_title = title.strip() if title is not None else rec.title
    new_capacity = capacity if capacity is not None else rec.capacity
    _validate(new_title, new_start, new_end, new_capacity)

    row.title, row.start, row.end, row.capacity = new_title, new_start, new_end, new_capacity
    if location is not None:
        row.location = location.strip()
    names = _set_tags(db, event_id, tags) if tags is not None else rec.tags
    db.commit()

    moved = new_start != rec.start
    with _lock:
        if moved:
            _tree.delete(rec.key)
        rec.title, rec.start, rec.end, rec.location = new_title, new_start, new_end, row.location
        rec.capacity, rec.tags = new_capacity, names
        _tree.insert(rec.key, rec)  # same key: just overwrites the value

    if moved:
        for pse in _registered(db, event_id):
            notify.cancel(db, _reminder_ref(event_id, pse))
            _schedule_reminder(db, rec, pse)
    _promote(db, rec)
    _changed(event_id, names)
    return rec


def remove(db: Session, event_id: int) -> None:
    """Delete the event, its registrations and their pending reminders."""
    rec = get(event_id)
    registered = _registered(db, event_id)
    db.execute(delete(Registration).where(Registration.event_id == event_id))
    db.execute(delete(ItemTag).where(ItemTag.item == f"e:{event_id}"))
    db.execute(delete(Event).where(Event.id == event_id))
    db.commit()
    for pse in registered:
        notify.cancel(db, _reminder_ref(event_id, pse))
    with _lock:
        _tree.delete(rec.key)
        _records.remove(event_id)
        if _queues.contains(event_id):
            queue = _queues.remove(event_id)
            while not queue.is_empty():
                pse, _ = queue.dequeue()
                if _waiting.contains((event_id, pse)):
                    _waiting.remove((event_id, pse))
    _changed(event_id, None)


def _registered(db: Session, event_id: int) -> list[str]:
    return list(db.scalars(select(Registration.pseudonym).where(
        Registration.event_id == event_id, Registration.status == "registered")))


# --- students: register / unregister --------------------------------------------------------------

def register(db: Session, event_id: int, pseudonym: str) -> str:
    """Register, or join the event's waitlist when it is full. Returns "registered" or "waitlisted"."""
    global _next_position
    rec = get(event_id)
    if rec.start <= clock.now():
        raise ValueError("this event has already started")
    row = db.scalar(select(Registration).where(Registration.event_id == event_id,
                                               Registration.pseudonym == pseudonym))
    if row is not None and row.status in ("registered", "waitlisted"):
        raise RegistrationConflict(f"already {row.status}")

    with _lock:
        status = "registered" if rec.registered < rec.capacity else "waitlisted"
        position = _next_position
        _next_position += 1
        if row is None:
            row = Registration(event_id=event_id, pseudonym=pseudonym)
            db.add(row)
        row.status, row.position = status, position
        db.commit()
        if status == "registered":
            rec.registered += 1
        else:
            rec.waitlisted += 1
            if not _queues.contains(event_id):
                _queues.put(event_id, Queue())
            _queues.get(event_id).enqueue((pseudonym, position))
            _waiting.put((event_id, pseudonym), position)

    if status == "registered":
        _schedule_reminder(db, rec, pseudonym)
    return status


def unregister(db: Session, event_id: int, pseudonym: str) -> None:
    """Leave the event or its waitlist. A freed place goes to the head of the waitlist."""
    rec = get(event_id)
    row = db.scalar(select(Registration).where(Registration.event_id == event_id,
                                               Registration.pseudonym == pseudonym))
    if row is None or row.status not in ("registered", "waitlisted"):
        raise EventNotFound(event_id)
    was = row.status
    row.status = "cancelled"
    db.commit()
    with _lock:
        if was == "registered":
            rec.registered -= 1
        else:
            rec.waitlisted -= 1
            if _waiting.contains((event_id, pseudonym)):
                _waiting.remove((event_id, pseudonym))  # its queue entry is now stale
    if was == "registered":
        notify.cancel(db, _reminder_ref(event_id, pseudonym))
        _promote(db, rec)


def _promote(db: Session, rec: EventRecord) -> None:
    """Move people from the head of the queue into free places, while the event hasn't started."""
    if rec.start <= clock.now():
        return
    while True:
        with _lock:
            queue = _queues.get(rec.id)
            if rec.registered >= rec.capacity or queue is None or queue.is_empty():
                return
            pse, position = queue.peek()
            if _waiting.get((rec.id, pse)) != position:  # left the waitlist: drop the stale entry
                queue.dequeue()
                continue
        row = db.scalar(select(Registration).where(Registration.event_id == rec.id,
                                                   Registration.pseudonym == pse))
        row.status = "registered"
        db.commit()
        with _lock:
            queue.dequeue()
            _waiting.remove((rec.id, pse))
            rec.waitlisted -= 1
            rec.registered += 1
        _schedule_reminder(db, rec, pse)
        notify.send_now(db, pse, "event_promoted", {
            "title": f"You're in: {rec.title}",
            "body": f"A place opened up and you have been moved off the waitlist. {_when(rec)}.",
            "event_id": rec.id})


# --- reminders -------------------------------------------------------------------------------------

def _reminder_ref(event_id: int, pseudonym: str) -> str:
    return f"event:{event_id}:{pseudonym}"


def _when(rec: EventRecord) -> str:
    text = clock.to_local(rec.start).strftime("%a %d %b, %H:%M")
    return f"{text}, {rec.location}" if rec.location else text


def _schedule_reminder(db: Session, rec: EventRecord, pseudonym: str) -> None:
    at = rec.start - REMINDER_BEFORE
    if at > clock.now():
        notify.schedule(db, pseudonym, "event_reminder",
                        {"title": f"{rec.title} starts in 1 hour", "body": _when(rec), "event_id": rec.id},
                        at, _reminder_ref(rec.id, pseudonym))
