"""seed_booking.py: the booking demo data follows the app's rules and gives every page something to show."""

from datetime import timedelta

from sqlalchemy import func, select

import seed_booking
from app import clock
from app.models import Availability, Booking, Notification
from app.services import booking, waitlist


def _seeded(db):
    booking.rebuild(db)
    waitlist.rebuild(db)
    return seed_booking.seed(db)


def test_seed_makes_the_demo_week(db):
    made = _seeded(db)
    assert made["counsellors"] == 3
    assert made["past_sessions"] > 20 and made["upcoming_sessions"] > 20
    noor, mehta, farouk = booking.counsellors()
    assert farouk.id == made["full_counsellor_id"]

    # the others have free time this week; Ms Farouk has none, so her line could be joined
    assert booking.has_free_time(noor.id, timedelta(days=7))
    assert booking.has_free_time(mehta.id, timedelta(days=7))
    assert not booking.has_free_time(farouk.id, timedelta(days=7))
    assert waitlist.counts(farouk.id) == {"urgent": 2, "normal": 4, "any_urgent": 0, "any_normal": 0}

    # history for "My sessions" and the counsellor's day, and Dr Noor's Wednesday meeting
    past = db.scalars(select(Booking).where(Booking.end <= clock.now())).all()
    assert past and {b.status for b in past} <= {"completed", "no_show"}
    assert db.scalar(select(func.count()).select_from(Availability).where(Availability.kind == "blocked")) >= 1

    # booking through the service told the counsellors and scheduled reminders
    assert db.scalar(select(func.count()).select_from(Notification)) > 0


def test_no_double_booking_anywhere(db):
    _seeded(db)
    active = db.scalars(select(Booking).where(Booking.status == "active")).all()
    for key in ("counsellor_id", "pseudonym"):
        groups = {}
        for b in active:
            groups.setdefault(getattr(b, key), []).append(b)
        for rows in groups.values():
            rows.sort(key=lambda b: b.start)
            assert all(a.end <= b.start for a, b in zip(rows, rows[1:]))


def test_cancelling_a_farouk_session_offers_it_to_the_line(db):
    made = _seeded(db)
    farouk = made["full_counsellor_id"]
    first = db.scalars(select(Booking).where(Booking.counsellor_id == farouk, Booking.status == "active",
                                             Booking.start > clock.now() + timedelta(hours=2))
                       .order_by(Booking.start)).first()
    booking.cancel(db, first.id, pseudonym=first.pseudonym)
    assert waitlist.counts(farouk)["urgent"] == 1  # the first urgent student now holds an offer


def test_seed_runs_once_and_survives_a_restart(db):
    _seeded(db)
    before = [booking.free_day(c.id, clock.to_local(clock.now()).date() + timedelta(days=1))
              for c in booking.counsellors()]
    assert seed_booking.seed(db) is None  # counsellors exist: nothing new
    booking.rebuild(db)
    waitlist.rebuild(db)
    after = [booking.free_day(c.id, clock.to_local(clock.now()).date() + timedelta(days=1))
             for c in booking.counsellors()]
    assert before == after
