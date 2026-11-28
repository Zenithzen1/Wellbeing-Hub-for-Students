"""Booking and waitlist demo data: the booking part of seed.py (plan section 12). Owner: Aditya.

    python seed_booking.py      (from backend/; on its own, with placeholder accounts)

What it makes, all fake:
  - 3 counsellors with weekday open hours for the next two weeks, and a staff meeting on Wednesdays;
  - last week's sessions (completed, a few no-shows), so "My sessions" and the counsellor's day have history;
  - this week about a third of Dr Noor's and Dr Mehta's times booked, so the Book page has free and busy times;
  - Ms Farouk fully booked for 8 days, with 6 students in her waitlist (2 urgent), so the waitlist and
    offer flow can be shown: cancel one of her sessions and the first student in line gets an offer.

seed.py should call seed(db, counsellor_accounts=[...3 staff account ids...], students=[...pseudonyms...])
once the account table and pseudonyms exist (Rithwik's part). Until then this file runs on its own with
placeholder account ids and made-up pseudonyms. It does nothing if counsellors already exist.

Future sessions and windows go through the booking and waitlist services, so they follow the same rules as
the app and land in the interval trees and heaps. Past rows are written straight to the database, because
the services (rightly) refuse to book or open time in the past.
"""

import hashlib
import random
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Availability, Booking, Counsellor
from app.services import booking, waitlist

# name, specialties, daily open hours (Dubai time), Wednesday staff meeting (or None)
COUNSELLORS = [
    ("Dr Noor Haddad", ["anxiety", "academic stress"], [(9, 13), (14, 17)], (12, 13)),
    ("Dr Arjun Mehta", ["sleep", "low mood"], [(10, 16)], None),
    ("Ms Leila Farouk", ["relationships", "low mood"], [(9, 12), (13, 16)], None),
]
FULL = 2               # index of the counsellor who is fully booked (the waitlist demo)
DAYS_AHEAD = 14        # open hours from today
BOOKED_DAYS = 7        # days with booked sessions for the others
FULL_DAYS = 9          # covers the waitlist's 7-day "no free time" rule with a day to spare
BOOK_SHARE = 0.35      # share of free starts booked for the others
FIRST_VISIT_SHARE = 0.2
WAITING = 6            # students in Ms Farouk's line
URGENT = 2             # of whom this many said "within 48 hours"

PLACEHOLDER_ACCOUNTS = [9001, 9002, 9003]


def fake_students(n: int = 40) -> list[str]:
    """Made-up pseudonyms, shaped like real ones (64 hex characters)."""
    return [hashlib.sha256(f"demo-student-{i}".encode()).hexdigest() for i in range(n)]


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=clock.DUBAI)


def _weekdays(first: date, last: date) -> list[date]:
    """Monday to Friday dates from first to last, inclusive."""
    days = []
    day = first
    while day <= last:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _past_week(db: Session, cids: list[int], students: Sequence[str], rng: random.Random, today: date) -> int:
    """Last week's open hours and sessions, written directly (the services refuse past times)."""
    made = 0
    for day in _weekdays(today - timedelta(days=7), today - timedelta(days=1)):
        for cid, (_, _, hours, _) in zip(cids, COUNSELLORS):
            for h0, h1 in hours:
                db.add(Availability(counsellor_id=cid, start=_at(day, h0), end=_at(day, h1), kind="open"))
                t = _at(day, h0)
                while t + booking.SESSION <= _at(day, h1):
                    if rng.random() < 0.5:
                        first = rng.random() < FIRST_VISIT_SHARE
                        end = t + (booking.FIRST_VISIT if first else booking.SESSION)
                        if end > _at(day, h1):
                            break
                        db.add(Booking(counsellor_id=cid, pseudonym=rng.choice(students), start=t, end=end,
                                       reason=rng.choice(booking.REASONS), first_visit=first,
                                       status="no_show" if rng.random() < 0.1 else "completed",
                                       revealed=False, created_at=t - timedelta(days=rng.randint(1, 6))))
                        made += 1
                        t = end
                    else:
                        t += booking.SESSION
    db.commit()
    return made


def _book(db: Session, cid: int, start: datetime, students: Sequence[str], rng: random.Random) -> bool:
    """Book `start` for some student who is free then. False if nobody could take it.

    Tries up to 8 random students, because some already have a session at that time. A first visit
    (60 minutes) may not fit before the next session; then we try a normal 45-minute one."""
    for pse in rng.sample(list(students), min(8, len(students))):
        reason = rng.choice(booking.REASONS)
        if rng.random() < FIRST_VISIT_SHARE:
            try:
                booking.book(db, pse, cid, start, reason, first_visit=True)
                return True
            except (booking.SlotTaken, ValueError):
                pass  # 60 minutes don't fit, or this student is busy: try 45 minutes below
        try:
            booking.book(db, pse, cid, start, reason, first_visit=False)
            return True
        except (booking.SlotTaken, ValueError):
            pass  # this student already has a session then: try the next one
    return False


def seed(db: Session, counsellor_accounts: Sequence[int] = PLACEHOLDER_ACCOUNTS,
         students: Sequence[str] | None = None, rng_seed: int = 2026) -> dict | None:
    """Create the booking and waitlist demo data. Returns what it made, or None if counsellors exist.

    The booking and waitlist structures must be loaded (services.rebuild_all() or booking.rebuild +
    waitlist.rebuild), as they are when the app starts.
    """
    if db.scalar(select(Counsellor.id).limit(1)) is not None:
        return None
    if len(counsellor_accounts) != len(COUNSELLORS):
        raise ValueError(f"need {len(COUNSELLORS)} counsellor account ids")
    students = list(students) if students is not None else fake_students()
    rng = random.Random(rng_seed)
    today = clock.to_local(clock.now()).date()

    cids = []
    for account_id, (name, specialties, _hours, _meeting) in zip(counsellor_accounts, COUNSELLORS):
        cids.append(booking.add_counsellor(db, account_id, name, specialties).id)
    past = _past_week(db, cids, students, rng, today)

    # open hours for the next two weeks (a window already over today is skipped)
    now = clock.now()
    for day in _weekdays(today, today + timedelta(days=DAYS_AHEAD - 1)):
        for cid, (_, _, hours, meeting) in zip(cids, COUNSELLORS):
            for h0, h1 in hours:
                if _at(day, h1) > now:
                    booking.add_availability(db, cid, _at(day, h0), _at(day, h1))
            if meeting and day.weekday() == 2 and _at(day, meeting[1]) > now:
                booking.add_availability(db, cid, _at(day, meeting[0]), _at(day, meeting[1]), "blocked",
                                         "Staff meeting")

    # Dr Noor and Dr Mehta: book about a third of this week's free starts
    upcoming = 0
    full = cids[FULL]
    for cid in cids:
        if cid == full:
            continue
        for day in _weekdays(today, today + timedelta(days=BOOKED_DAYS - 1)):
            for start in booking.free_day(cid, day)["starts"]:
                if rng.random() < BOOK_SHARE and _book(db, cid, start, students, rng):
                    upcoming += 1

    # Ms Farouk: keep booking her earliest free start until the day has none left
    for day in _weekdays(today, today + timedelta(days=FULL_DAYS - 1)):
        while True:
            starts = booking.free_day(full, day)["starts"]
            if not starts or not _book(db, full, starts[0], students, rng):
                break
            upcoming += 1

    # her waitlist: 6 students who have no session with her, the first 2 urgent
    has_session = set(db.scalars(select(Booking.pseudonym).where(Booking.counsellor_id == full,
                                                                 Booking.status == "active")))
    waiting = 0
    for pse in students:
        if waiting == WAITING:
            break
        if pse not in has_session:
            waitlist.join(db, pse, full, urgent=waiting < URGENT)
            waiting += 1

    return {"counsellors": len(cids), "past_sessions": past, "upcoming_sessions": upcoming,
            "waiting": waiting, "full_counsellor_id": full}


def main() -> None:
    from app import services
    from app.db import SessionLocal, init_db

    init_db()
    services.rebuild_all()
    db = SessionLocal()
    try:
        made = seed(db)
    finally:
        db.close()
    if made is None:
        print("counsellors already exist; nothing seeded")
    else:
        print("seeded:", made)


if __name__ == "__main__":
    main()
