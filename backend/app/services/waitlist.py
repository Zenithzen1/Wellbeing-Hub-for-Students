"""Waitlist: indexed min-heap keyed (tier, join time) with ageing; offers and expiry. Owner: Aditya.

Plan section 5.
* One IndexedMinHeap per line: counsellor id -> heap, plus ANY for the "any counsellor" line.
  Heap id = waitlist entry id; key = (tier, joined_at, entry id). Tier 0 (urgent, or aged) goes first,
  then first come first served; the id only breaks exact ties. The heap's position map makes leave,
  ageing and "remove me from my other lines" O(log n).
* A cancellation calls offer_freed(): peek at the counsellor's heap and the ANY heap, take whichever top
  key is smaller, hold the time in the counsellor's interval tree, and offer it for
  min(30 min, half the time left before the session).
* The offer's expiry is a job in the timed heap ("offer_expiry", see services/notify.py).
  First timeout: the time passes to the next person and the student goes back with their original key.
  Second timeout, or a decline: the student is removed. Accept: a booking is made, and the student
  leaves every other line. When nobody is left in line, the hold is released and everyone sees the time.
* Ageing: an hourly job ("waitlist_ageing") moves tier-1 entries older than 72 h to tier 0, keeping
  their join time.

Write-through: the database commits first, then the heaps change.
Errors: EntryNotFound, OfferNotFound (-> 404), WaitlistConflict, OfferGone (-> 409).
"""

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.ds import HashMap, IndexedMinHeap
from app.models import Offer, WaitlistEntry
from app.services import booking, notify

ANY = "any"                         # heap name for the "any counsellor" line
URGENT, NORMAL = 0, 1               # tiers
HOLD = timedelta(minutes=30)
MIN_HOLD = timedelta(minutes=5)     # less time than this before the session: don't offer, just free it
AGEING_AFTER = timedelta(hours=72)
AGEING_EVERY = timedelta(hours=1)
FREE_HORIZON = timedelta(days=7)    # you can join a line only if there is no free time this soon
MAX_MISSES = 2                      # the 2nd ignored offer removes you
EXPIRY_JOB, AGEING_JOB = "offer_expiry", "waitlist_ageing"


class EntryNotFound(KeyError):
    pass


class OfferNotFound(KeyError):
    pass


class WaitlistConflict(Exception):
    pass


class OfferGone(Exception):
    """The offer is no longer open (expired, declined, accepted or withdrawn)."""


@dataclass
class EntryRecord:
    id: int
    counsellor_id: int | None
    pseudonym: str
    tier: int
    joined_at: datetime
    misses: int
    status: str  # waiting | offered

    @property
    def key(self) -> tuple:
        return (self.tier, self.joined_at, self.id)

    @property
    def line(self):
        return ANY if self.counsellor_id is None else self.counsellor_id


_lock = threading.RLock()
_heaps = HashMap()       # line (counsellor id or ANY) -> IndexedMinHeap of entry id -> key
_entries = HashMap()     # entry id -> EntryRecord, for entries that are waiting or offered
_by_student = HashMap()  # pseudonym -> list of their entry ids (waiting or offered)


# --- startup ----------------------------------------------------------------------------------------

def rebuild(db: Session) -> None:
    """Heaps from waiting entries; expiry jobs for open offers; the ageing job. Runs after booking.rebuild
    (which already put the open offers' holds into the interval trees)."""
    global _heaps, _entries, _by_student
    heaps, entries, by_student, items = HashMap(), HashMap(), HashMap(), HashMap()
    for row in db.scalars(select(WaitlistEntry).where(WaitlistEntry.status.in_(("waiting", "offered")))):
        rec = EntryRecord(row.id, row.counsellor_id, row.pseudonym, row.tier, row.joined_at, row.misses, row.status)
        entries.put(rec.id, rec)
        if not by_student.contains(rec.pseudonym):
            by_student.put(rec.pseudonym, [])
        by_student.get(rec.pseudonym).append(rec.id)
        if rec.status == "waiting":
            if not items.contains(rec.line):
                items.put(rec.line, [])
            items.get(rec.line).append((rec.id, rec.key))
    for line, pairs in items.items():
        heap = IndexedMinHeap()
        heap.build_heap(pairs)  # O(n) bottom-up
        heaps.put(line, heap)
    with _lock:
        _heaps, _entries, _by_student = heaps, entries, by_student

    for offer in db.scalars(select(Offer).where(Offer.status == "open")):
        notify.schedule_job(EXPIRY_JOB, str(offer.id), offer.expires_at)  # already late -> next tick
    notify.schedule_job(AGEING_JOB, "all", clock.now())


def _heap(line) -> IndexedMinHeap:
    heap = _heaps.get(line)
    if heap is None:
        heap = IndexedMinHeap()
        _heaps.put(line, heap)
    return heap


def _track(rec: EntryRecord) -> None:
    _entries.put(rec.id, rec)
    if not _by_student.contains(rec.pseudonym):
        _by_student.put(rec.pseudonym, [])
    _by_student.get(rec.pseudonym).append(rec.id)


def _drop(rec: EntryRecord | None) -> None:
    """Forget an entry that is no longer waiting or offered."""
    if rec is None:
        return
    heap = _heaps.get(rec.line)
    if heap is not None and heap.contains(rec.id):
        heap.remove(rec.id)
    if _entries.contains(rec.id):
        _entries.remove(rec.id)
    ids = _by_student.get(rec.pseudonym)
    if ids is not None and rec.id in ids:
        ids.remove(rec.id)
        if not ids:
            _by_student.remove(rec.pseudonym)


# --- students: join / view / leave ----------------------------------------------------------------------

def join(db: Session, pseudonym: str, counsellor_id: int | None = None, urgent: bool = False) -> EntryRecord:
    """Join a counsellor's line, or the "any counsellor" line when counsellor_id is None.

    urgent = "I need to talk to someone within 48 hours" (self-triage, tier 0).
    """
    if counsellor_id is not None:
        booking.get_counsellor(counsellor_id)
    with _lock:
        for eid in _by_student.get(pseudonym, []):
            if _entries.get(eid).counsellor_id == counsellor_id:
                raise WaitlistConflict("you are already on this waitlist")
    ids = [counsellor_id] if counsellor_id is not None else [c.id for c in booking.counsellors()]
    if any(booking.has_free_time(cid, FREE_HORIZON) for cid in ids):
        raise WaitlistConflict("there is free time in the next 7 days; please book a session instead")

    row = WaitlistEntry(counsellor_id=counsellor_id, pseudonym=pseudonym, tier=URGENT if urgent else NORMAL,
                        joined_at=clock.now(), misses=0, status="waiting")
    db.add(row)
    db.commit()
    rec = EntryRecord(row.id, row.counsellor_id, pseudonym, row.tier, row.joined_at, 0, "waiting")
    with _lock:
        _track(rec)
        _heap(rec.line).push(rec.id, rec.key)
    return rec


def _ahead(rec: EntryRecord) -> int:
    """How many people are before this entry in its line. O(n), for display only."""
    if rec.status != "waiting":
        return 0
    return sum(1 for other in _entries.values()
               if other.status == "waiting" and other.line == rec.line and other.key < rec.key)


def my_entries(db: Session, pseudonym: str) -> list[dict]:
    """The student's lines, with their place in each and any open offer."""
    with _lock:
        recs = [_entries.get(eid) for eid in _by_student.get(pseudonym, [])]
        ahead = [_ahead(rec) for rec in recs]
    out = []
    for rec, n in zip(recs, ahead):
        offer = db.scalar(select(Offer).where(Offer.waitlist_id == rec.id, Offer.status == "open"))
        out.append(to_dict(rec, n, offer))
    return sorted(out, key=lambda d: d["joined_at"])


def leave(db: Session, pseudonym: str, entry_id: int) -> None:
    """Leave a line. If the student holds an offer from it, the offer is withdrawn and passed on."""
    with _lock:
        rec = _entries.get(entry_id)
    if rec is None or rec.pseudonym != pseudonym:
        raise EntryNotFound(entry_id)
    offer = db.scalar(select(Offer).where(Offer.waitlist_id == entry_id, Offer.status == "open"))
    if offer is not None:
        _close_offer(db, offer, "withdrawn", "left")
        return
    row = db.get(WaitlistEntry, entry_id)
    row.status = "left"
    db.commit()
    with _lock:
        _drop(rec)


def counts(counsellor_id: int) -> dict:
    """Counsellor view: how many are waiting, without saying who."""
    booking.get_counsellor(counsellor_id)
    out = {"urgent": 0, "normal": 0, "any_urgent": 0, "any_normal": 0}
    with _lock:
        for rec in _entries.values():
            if rec.status != "waiting":
                continue
            prefix = "" if rec.line == counsellor_id else "any_" if rec.line == ANY else None
            if prefix is not None:
                out[prefix + ("urgent" if rec.tier == URGENT else "normal")] += 1
    return out


# --- offers ---------------------------------------------------------------------------------------------

def _pick(counsellor_id: int) -> EntryRecord | None:
    """The front of the counsellor's line or of the ANY line, whichever key is smaller. Two O(1) peeks."""
    best = None
    for line in (counsellor_id, ANY):
        heap = _heaps.get(line)
        if heap is not None and len(heap):
            eid, key = heap.peek()
            if best is None or key < best[1]:
                best = (eid, key)
    return None if best is None else _entries.get(best[0])


def offer_freed(db: Session, counsellor_id: int, start: datetime, end: datetime) -> bool:
    """Called by booking.cancel inside the counsellor's lock, once the session has left the tree.
    True if someone was offered the time (it is now held for them)."""
    return _offer_next(db, counsellor_id, start, end)


def _offer_next(db: Session, counsellor_id: int, start: datetime, end: datetime) -> bool:
    hold = min(HOLD, (start - clock.now()) / 2)
    if hold < MIN_HOLD:
        return False
    with _lock:
        rec = _pick(counsellor_id)
        if rec is None:
            return False
        row = db.get(WaitlistEntry, rec.id)
        row.status = "offered"
        offer = Offer(waitlist_id=rec.id, counsellor_id=counsellor_id, start=start, end=end,
                      expires_at=clock.now() + hold, status="open")
        db.add(offer)
        db.commit()
        _heaps.get(rec.line).remove(rec.id)
        rec.status = "offered"
    booking.hold(db, counsellor_id, start, end, offer.id)
    notify.schedule_job(EXPIRY_JOB, str(offer.id), offer.expires_at)
    data = offer_dict(offer)
    minutes = max(1, int(hold.total_seconds() // 60))
    notify.send_now(db, rec.pseudonym, "waitlist_offer",
                    {"title": "A session opened up for you",
                     "body": f"{data['counsellor_name']}, {clock.to_local(start).strftime('%a %d %b, %H:%M')}. "
                             f"Accept within {minutes} minutes or it goes to the next person.",
                     "offer_id": offer.id, "expires_at": offer.expires_at.isoformat()},
                    ref=f"offer:{offer.id}")
    notify.publish(rec.pseudonym, "offer", data)
    return True


def _pass_on(db: Session, offer: Offer) -> None:
    """The time in this offer goes to the next person in line, or is released to everyone."""
    if not _offer_next(db, offer.counsellor_id, offer.start, offer.end):
        booking.release(db, offer.counsellor_id, offer.start, offer.end)


def _close_offer(db: Session, offer: Offer, offer_status: str, entry_status: str) -> None:
    """Decline or withdraw: close the offer, take the student out of that line, pass the time on."""
    with booking.lock_for(offer.counsellor_id):
        row = db.get(WaitlistEntry, offer.waitlist_id)
        offer.status = offer_status
        row.status = entry_status
        db.commit()
        notify.cancel_job(EXPIRY_JOB, str(offer.id))
        with _lock:
            _drop(_entries.get(row.id))
        _pass_on(db, offer)


def _expire(db: Session, offer: Offer) -> None:
    """Timeout. The time goes to the next person first; then the student goes back in line with their
    original key, unless this was their second miss."""
    with booking.lock_for(offer.counsellor_id):
        row = db.get(WaitlistEntry, offer.waitlist_id)
        offer.status = "expired"
        row.misses += 1
        back = row.misses < MAX_MISSES
        row.status = "waiting" if back else "removed"
        db.commit()
        with _lock:
            rec = _entries.get(row.id)
        _pass_on(db, offer)
        with _lock:
            if rec is not None and back:
                rec.status, rec.misses = "waiting", row.misses
                _heap(rec.line).push(rec.id, rec.key)
            elif rec is not None:
                _drop(rec)
    if not back:
        notify.send_now(db, row.pseudonym, "waitlist_removed",
                        {"title": "Removed from the waitlist",
                         "body": "You missed two offers, so you have been taken off this waitlist. "
                                 "You can join again at any time."})


def _on_offer_expiry(db: Session, ref: str) -> None:
    offer = db.get(Offer, int(ref))
    if offer is not None and offer.status == "open":
        _expire(db, offer)


def _open_offer_for(db: Session, pseudonym: str, offer_id: int) -> tuple[Offer, WaitlistEntry]:
    offer = db.get(Offer, offer_id)
    entry = db.get(WaitlistEntry, offer.waitlist_id) if offer is not None else None
    if offer is None or entry is None or entry.pseudonym != pseudonym:
        raise OfferNotFound(offer_id)
    if offer.status != "open":
        raise OfferGone(f"this offer was {offer.status}")
    if offer.expires_at <= clock.now():  # the expiry job just hasn't run yet
        _expire(db, offer)
        raise OfferGone("this offer has expired")
    return offer, entry


def accept(db: Session, pseudonym: str, offer_id: int, reason: str = "other", reveal: bool = False,
           identity_blob: str | None = None):
    """Book the offered time. The student then leaves every other line (and any other offers pass on)."""
    offer, entry = _open_offer_for(db, pseudonym, offer_id)

    def close(b):
        offer.status, offer.booking_id, entry.status = "accepted", b.id, "booked"

    row = booking.book_from_offer(db, offer, pseudonym, reason, reveal, identity_blob, before_commit=close)
    notify.cancel_job(EXPIRY_JOB, str(offer.id))
    with _lock:
        _drop(_entries.get(entry.id))
        others = list(_by_student.get(pseudonym, []))
    for eid in others:
        try:
            leave(db, pseudonym, eid)
        except EntryNotFound:
            pass
    return row


def decline(db: Session, pseudonym: str, offer_id: int) -> None:
    """Say no: removed from that line straight away, and the time goes to the next person."""
    offer, _ = _open_offer_for(db, pseudonym, offer_id)
    _close_offer(db, offer, "declined", "removed")


def offer_dict(offer: Offer) -> dict:
    try:
        name = booking.get_counsellor(offer.counsellor_id).display_name
    except booking.CounsellorNotFound:
        name = ""
    return {"id": offer.id, "counsellor_id": offer.counsellor_id, "counsellor_name": name, "start": offer.start,
            "end": offer.end, "expires_at": offer.expires_at, "status": offer.status}


def to_dict(rec: EntryRecord, ahead: int = 0, offer: Offer | None = None) -> dict:
    name = None
    if rec.counsellor_id is not None:
        try:
            name = booking.get_counsellor(rec.counsellor_id).display_name
        except booking.CounsellorNotFound:
            name = ""
    return {"id": rec.id, "counsellor_id": rec.counsellor_id, "counsellor_name": name, "urgent": rec.tier == URGENT,
            "joined_at": rec.joined_at, "status": rec.status, "misses": rec.misses, "ahead": ahead,
            "offer": offer_dict(offer) if offer is not None else None}


# --- ageing -------------------------------------------------------------------------------------------------

def age(db: Session) -> int:
    """Promote tier-1 entries that have waited over 72 h to tier 0 (same join time). Returns how many."""
    cutoff = clock.now() - AGEING_AFTER
    with _lock:
        due = [rec for rec in _entries.values() if rec.tier == NORMAL and rec.joined_at <= cutoff]
    if not due:
        return 0
    for rec in due:
        db.get(WaitlistEntry, rec.id).tier = URGENT
    db.commit()
    with _lock:
        for rec in due:
            rec.tier = URGENT
            heap = _heaps.get(rec.line)
            if heap is not None and heap.contains(rec.id):
                heap.update(rec.id, rec.key)  # smaller key: sifts up
    return len(due)


def _on_ageing(db: Session, ref: str) -> None:
    try:
        age(db)
    finally:
        notify.schedule_job(AGEING_JOB, ref, clock.now() + AGEING_EVERY)


notify.register_job(EXPIRY_JOB, _on_offer_expiry)
notify.register_job(AGEING_JOB, _on_ageing)
