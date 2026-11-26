"""Booking service: interval-tree grid, no double booking, SQL safety net, cancellation, restart safety."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import clock
from app.models import Booking, Notification
from app.services import booking, notify, waitlist

from .conftest import T0  # Mon 30 Nov 2026, 10:00 Dubai

S = [f"{i:x}" * 64 for i in range(1, 10)]  # fake pseudonyms
TUE = date(2026, 12, 1)


def at(h, m=0, day=1):
    """Dubai time on 1 Dec 2026 (or another December day)."""
    return datetime(2026, 12, day, h, m, tzinfo=clock.DUBAI)


@pytest.fixture
def svc(db):
    """The services db plus fresh interval trees and heaps."""
    booking.rebuild(db)
    waitlist.rebuild(db)
    return db


@pytest.fixture
def noor(svc):
    rec = booking.add_counsellor(svc, 100, "Dr Noor", ["anxiety", " study "])
    booking.add_availability(svc, rec.id, at(9), at(17))
    return rec


def _book(db, cid, pse, h, m=0, first=False, reason="anxiety"):
    return booking.book(db, pse, cid, at(h, m), reason, first_visit=first)


def _plan_monday(db, cid):
    """The plan's worked example: sessions at 9, 10, 11, 14, 15:30 and a 13:00-13:45 block."""
    _book(db, cid, S[0], 9, first=True)        # 9:00-10:00
    _book(db, cid, S[1], 10)                   # 10:00-10:45
    _book(db, cid, S[2], 11, first=True)       # 11:00-12:00
    booking.add_availability(db, cid, at(13), at(13, 45), "blocked", "staff meeting")
    _book(db, cid, S[3], 14, first=True)       # 14:00-15:00
    _book(db, cid, S[4], 15, 30)               # 15:30-16:15


def _local_starts(grid):
    return [clock.to_local(t).strftime("%H:%M") for t in grid["starts"]]


def test_counsellor_profiles(noor):
    assert noor.specialties == ("anxiety", "study")
    assert [c.display_name for c in booking.counsellors()] == ["Dr Noor"]
    assert booking.counsellor_for_account(100).id == noor.id
    with pytest.raises(booking.CounsellorNotFound):
        booking.counsellor_for_account(999)


def test_free_grid_matches_the_plan(svc, noor):
    _plan_monday(svc, noor.id)
    grid = booking.free_day(noor.id, TUE)
    assert _local_starts(grid) == ["12:00", "12:15", "16:15"]
    assert len(grid["busy"]) == 6 and len(grid["open"]) == 1
    assert _local_starts(booking.free_day(noor.id, TUE, first_visit=True)) == ["12:00"]
    assert booking.free_day(noor.id, date(2026, 12, 2))["starts"] == []


def test_overlap_is_rejected_but_touching_is_fine(svc, noor):
    _plan_monday(svc, noor.id)
    with pytest.raises(booking.SlotTaken):
        _book(svc, noor.id, S[5], 11, 30)            # 11:30-12:15 hits 11:00-12:00
    assert _book(svc, noor.id, S[5], 12).end == at(12, 45).astimezone(T0.tzinfo)
    with pytest.raises(booking.SlotTaken):
        _book(svc, noor.id, S[6], 12, 15)            # now taken
    with pytest.raises(booking.SlotTaken):
        _book(svc, noor.id, S[6], 13, 30)            # hits the block


def test_validation(svc, noor):
    with pytest.raises(ValueError, match="quarter hour"):
        _book(svc, noor.id, S[0], 10, 10)
    with pytest.raises(ValueError, match="outside"):
        _book(svc, noor.id, S[0], 8)
    with pytest.raises(ValueError, match="outside"):
        _book(svc, noor.id, S[0], 16, 30)            # would end 17:15
    with pytest.raises(ValueError, match="reason"):
        _book(svc, noor.id, S[0], 10, reason="boredom")
    with pytest.raises(ValueError, match="passed"):
        booking.book(svc, S[0], noor.id, T0 - timedelta(hours=1), "anxiety")
    with pytest.raises(ValueError, match="ahead"):
        booking.book(svc, S[0], noor.id, T0 + timedelta(days=61), "anxiety")
    with pytest.raises(booking.CounsellorNotFound):
        booking.book(svc, S[0], 999, at(10), "anxiety")


def test_a_student_cannot_be_in_two_sessions_at_once(svc, noor):
    mehta = booking.add_counsellor(svc, 101, "Dr Mehta")
    booking.add_availability(svc, mehta.id, at(9), at(17))
    _book(svc, noor.id, S[0], 10)
    with pytest.raises(booking.SlotTaken, match="you already"):
        _book(svc, mehta.id, S[0], 10, 30)


def test_sql_recheck_catches_what_the_tree_missed(svc, noor):
    """If memory and disk ever disagree, the BEGIN IMMEDIATE re-check stops a double booking."""
    svc.add(Booking(counsellor_id=noor.id, pseudonym=S[8], start=at(10), end=at(10, 45), reason="other",
                    status="active", created_at=T0))
    svc.commit()  # behind the tree's back
    with pytest.raises(booking.SlotTaken):
        _book(svc, noor.id, S[0], 10, 15)
    assert svc.scalar(select(Booking).where(Booking.pseudonym == S[0])) is None
    _book(svc, noor.id, S[0], 11)  # the session still works afterwards


def test_booking_schedules_reminders_and_tells_the_counsellor(svc, noor, channel):
    b = _book(svc, noor.id, S[0], 12)
    rows = svc.scalars(select(Notification).where(Notification.status == "pending")).all()
    assert sorted(r.kind for r in rows) == ["session_booked", "session_reminder", "session_reminder"]
    notify.tick(svc)
    assert channel.sent == ["New session booked"]
    clock.advance(at(12) - timedelta(hours=24) - T0)
    notify.tick(svc)
    assert channel.sent[-1] == "Session in 24 hours"
    assert b.status == "active"


def test_cancel_frees_the_time_and_drops_reminders(svc, noor, channel):
    b = _book(svc, noor.id, S[0], 12)
    assert "12:00" not in _local_starts(booking.free_day(noor.id, TUE))
    with pytest.raises(booking.BookingNotFound):
        booking.cancel(svc, b.id, pseudonym=S[1])     # not yours: looks like it doesn't exist
    with pytest.raises(booking.BookingNotFound):
        booking.cancel(svc, b.id, counsellor_id=noor.id + 1)
    booking.cancel(svc, b.id, pseudonym=S[0])
    assert b.status == "cancelled" and b.cancelled_by == "student"
    assert "12:00" in _local_starts(booking.free_day(noor.id, TUE))
    assert svc.scalars(select(Notification).where(Notification.ref == f"booking:{b.id}",
                                                  Notification.status == "pending")).all() == []
    with pytest.raises(ValueError, match="already cancelled"):
        booking.cancel(svc, b.id, pseudonym=S[0])


def test_counsellor_cancel_tells_the_student(svc, noor, channel):
    b = _book(svc, noor.id, S[0], 12)
    booking.cancel(svc, b.id, counsellor_id=noor.id)
    notify.tick(svc)
    assert "Your session was cancelled" in channel.sent


def test_cannot_cancel_a_session_that_started_and_marking(svc, noor):
    b = _book(svc, noor.id, S[0], 10)
    with pytest.raises(ValueError, match="hasn't started"):
        booking.mark(svc, noor.id, b.id, "completed")
    clock.advance(at(10, 5) - T0)
    with pytest.raises(ValueError, match="already started"):
        booking.cancel(svc, b.id, pseudonym=S[0])
    assert booking.mark(svc, noor.id, b.id, "no_show").status == "no_show"
    assert booking.mark(svc, noor.id, b.id, "completed").status == "completed"
    with pytest.raises(booking.BookingNotFound):
        booking.mark(svc, noor.id + 1, b.id, "completed")


def test_availability_rules(svc, noor):
    with pytest.raises(booking.SlotTaken):
        booking.add_availability(svc, noor.id, at(16), at(18))                 # overlaps the 9-17 window
    late = booking.add_availability(svc, noor.id, at(17), at(19))               # touching is fine
    _book(svc, noor.id, S[0], 10)
    with pytest.raises(booking.SlotTaken):
        booking.add_availability(svc, noor.id, at(10, 30), at(11), "blocked")  # over a session
    block = booking.add_availability(svc, noor.id, at(12), at(13), "blocked")
    assert "12:00" not in _local_starts(booking.free_day(noor.id, TUE))
    booking.remove_availability(svc, noor.id, block.id)
    assert "12:00" in _local_starts(booking.free_day(noor.id, TUE))

    window = booking.list_availability(svc, noor.id, at(0), at(23))[0]
    with pytest.raises(booking.SlotTaken, match="cancel them first"):
        booking.remove_availability(svc, noor.id, window.id)
    booking.remove_availability(svc, noor.id, late.id)
    assert "17:00" not in _local_starts(booking.free_day(noor.id, TUE))
    with pytest.raises(booking.AvailabilityNotFound):
        booking.remove_availability(svc, noor.id, late.id)
    with pytest.raises(ValueError):
        booking.add_availability(svc, noor.id, at(20), at(19))
    with pytest.raises(ValueError):
        booking.add_availability(svc, noor.id, at(9, day=2), at(10, day=3))  # over 24 hours


def test_rebuild_answers_identically(svc, noor):
    _plan_monday(svc, noor.id)
    before = booking.free_day(noor.id, TUE)
    booking.rebuild(svc)
    assert booking.free_day(noor.id, TUE) == before
    with pytest.raises(booking.SlotTaken):
        _book(svc, noor.id, S[5], 11, 30)


def test_views(svc, noor):
    b = _book(svc, noor.id, S[0], 10)
    booking.book(svc, S[1], noor.id, at(11), "sleep", reveal=True, identity_blob="sealed")
    assert [booking.to_dict(r)["counsellor_name"] for r in booking.my_bookings(svc, S[0])] == ["Dr Noor"]
    sessions = [booking.to_session_dict(r, identity="Asha") for r in booking.sessions_on(svc, noor.id, TUE)]
    assert [s["student"] for s in sessions] == [booking.tag(S[0]), booking.tag(S[1])]
    assert sessions[0]["identity"] is None and sessions[1]["identity"] == "Asha"
    assert booking.tag(S[0]) == "#111111"
    booking.cancel(svc, b.id, pseudonym=S[0])
    assert len(booking.sessions_on(svc, noor.id, TUE)) == 1
