"""Waitlist service: fair order, offers with holds, timeouts, decline/accept, ageing, restart safety."""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app import clock
from app.models import Booking, Offer, WaitlistEntry
from app.services import booking, notify, waitlist

S = [f"{i:x}" * 64 for i in range(1, 16)]
A, B, C, D, E = S[10:15]   # the plan's five students
TUE = date(2026, 12, 1)


def at(h, m=0, day=1):
    return datetime(2026, 12, day, h, m, tzinfo=clock.DUBAI)


@pytest.fixture
def svc(db):
    booking.rebuild(db)
    waitlist.rebuild(db)
    return db


@pytest.fixture
def full(svc):
    """Dr Noor with one window, Tue 10:00-11:30, already fully booked by S[0] and S[1]."""
    noor = booking.add_counsellor(svc, 100, "Dr Noor")
    booking.add_availability(svc, noor.id, at(10), at(11, 30))
    first = booking.book(svc, S[0], noor.id, at(10), "anxiety")
    second = booking.book(svc, S[1], noor.id, at(10, 45), "sleep")
    return noor, first, second


def _join(db, pse, cid, urgent=False):
    clock.advance(timedelta(minutes=1))  # distinct join times
    return waitlist.join(db, pse, cid, urgent)


def _plan_line(db, cid):
    """C, A normal; B urgent; D normal; E urgent (plan section 5)."""
    return {name: _join(db, pse, cid, urgent=name in "BE")
            for name, pse in zip("CABDE", (C, A, B, D, E))}


def _open_offer(db, pse):
    return db.scalar(select(Offer).join(WaitlistEntry, WaitlistEntry.id == Offer.waitlist_id)
                     .where(WaitlistEntry.pseudonym == pse, Offer.status == "open"))


def _starts(cid):
    return [clock.to_local(t).strftime("%H:%M") for t in booking.free_day(cid, TUE)["starts"]]


def test_can_only_join_when_there_is_no_free_time(svc):
    noor = booking.add_counsellor(svc, 100, "Dr Noor")
    booking.add_availability(svc, noor.id, at(10), at(11))
    with pytest.raises(waitlist.WaitlistConflict, match="book a session"):
        waitlist.join(svc, A, noor.id)
    with pytest.raises(waitlist.WaitlistConflict):
        waitlist.join(svc, A, None)        # "any": someone has free time
    with pytest.raises(booking.CounsellorNotFound):
        waitlist.join(svc, A, 999)


def test_no_joining_the_same_line_twice(svc, full):
    noor, _, _ = full
    waitlist.join(svc, A, noor.id)
    with pytest.raises(waitlist.WaitlistConflict, match="already"):
        waitlist.join(svc, A, noor.id)
    waitlist.join(svc, A, None)            # the "any" line is a different line


def test_fair_order_leave_and_first_offer(svc, full, channel):
    noor, first, _ = full
    line = _plan_line(svc, noor.id)
    places = {e["id"]: e["ahead"] for pse in (C, A, B, D, E) for e in waitlist.my_entries(svc, pse)}
    assert [places[line[n].id] for n in "BECAD"] == [0, 1, 2, 3, 4]
    assert waitlist.counts(noor.id) == {"urgent": 2, "normal": 3, "any_urgent": 0, "any_normal": 0}

    with pytest.raises(waitlist.EntryNotFound):
        waitlist.leave(svc, A, line["D"].id)  # not A's entry
    waitlist.leave(svc, D, line["D"].id)
    booking.cancel(svc, first.id, pseudonym=S[0])

    offer = _open_offer(svc, B)
    assert offer is not None and offer.start == first.start
    assert offer.expires_at == clock.now() + timedelta(minutes=30)
    assert "10:00" not in _starts(noor.id)                      # held for B, nobody else sees it
    with pytest.raises(booking.SlotTaken):
        booking.book(svc, S[5], noor.id, at(10), "other")
    mine = waitlist.my_entries(svc, B)[0]
    assert mine["status"] == "offered" and mine["offer"]["id"] == offer.id
    notify.tick(svc)
    assert "A session opened up for you" in channel.sent


def test_any_counsellor_line_competes_on_key(svc, full):
    noor, first, _ = full
    waitlist.join(svc, C, noor.id)          # normal, earlier
    _join(svc, E, None, urgent=True)        # urgent in the "any" line wins
    booking.cancel(svc, first.id, pseudonym=S[0])
    assert _open_offer(svc, E) is not None and _open_offer(svc, C) is None


def test_timeout_passes_on_then_second_timeout_removes(svc, full, channel):
    noor, first, _ = full
    line = _plan_line(svc, noor.id)
    booking.cancel(svc, first.id, pseudonym=S[0])
    assert _open_offer(svc, B) is not None

    clock.advance(timedelta(minutes=31))
    notify.tick(svc)                                         # B's offer expires -> E, B keeps their place
    assert _open_offer(svc, B) is None and _open_offer(svc, E) is not None
    b_entry = svc.get(WaitlistEntry, line["B"].id)
    assert (b_entry.status, b_entry.misses) == ("waiting", 1)
    assert waitlist.my_entries(svc, B)[0]["ahead"] == 0       # still at the front

    waitlist.decline(svc, E, _open_offer(svc, E).id)           # E declines -> removed; B is next again
    assert svc.get(WaitlistEntry, line["E"].id).status == "removed"
    assert _open_offer(svc, B) is not None
    with pytest.raises(waitlist.OfferGone):
        waitlist.decline(svc, E, svc.scalars(select(Offer).where(Offer.status == "declined")).first().id)

    clock.advance(timedelta(minutes=31))
    notify.tick(svc)                                         # B's second miss removes them; C is next
    assert svc.get(WaitlistEntry, line["B"].id).status == "removed"
    assert _open_offer(svc, C) is not None
    notify.tick(svc)
    assert "Removed from the waitlist" in channel.sent


def test_accept_books_and_leaves_every_other_line(svc, full):
    noor, first, _ = full
    mehta = booking.add_counsellor(svc, 101, "Dr Mehta")
    waitlist.join(svc, B, noor.id, urgent=True)
    waitlist.join(svc, B, mehta.id)
    waitlist.join(svc, B, None)
    booking.cancel(svc, first.id, pseudonym=S[0])
    offer = _open_offer(svc, B)

    with pytest.raises(waitlist.OfferNotFound):
        waitlist.accept(svc, A, offer.id)                     # someone else's offer
    b = waitlist.accept(svc, B, offer.id, "low_mood")
    assert (b.status, b.pseudonym, b.start, b.reason) == ("active", B, first.start, "low_mood")
    assert offer.status == "accepted" and offer.booking_id == b.id
    assert waitlist.my_entries(svc, B) == []
    assert sorted(e.status for e in svc.scalars(select(WaitlistEntry).where(WaitlistEntry.pseudonym == B))) == \
        ["booked", "left", "left"]
    with pytest.raises(waitlist.OfferGone):
        waitlist.accept(svc, B, offer.id)
    clock.advance(timedelta(hours=1))
    notify.tick(svc)                                           # the expiry job was cancelled: nothing changes
    assert svc.get(Booking, b.id).status == "active"
    assert "10:00" not in _starts(noor.id)


def test_accepting_too_late_counts_as_a_timeout(svc, full):
    noor, first, _ = full
    waitlist.join(svc, B, noor.id)
    booking.cancel(svc, first.id, pseudonym=S[0])
    offer = _open_offer(svc, B)
    clock.advance(timedelta(minutes=30))                       # expired, but the tick hasn't run yet
    with pytest.raises(waitlist.OfferGone, match="expired"):
        waitlist.accept(svc, B, offer.id)
    assert "10:00" in _starts(noor.id)                         # nobody else waiting: shown to everyone


def test_leaving_with_an_open_offer_passes_it_on(svc, full):
    noor, first, _ = full
    b_entry = waitlist.join(svc, B, noor.id, urgent=True)
    _join(svc, C, noor.id)
    booking.cancel(svc, first.id, pseudonym=S[0])
    waitlist.leave(svc, B, b_entry.id)
    assert svc.scalar(select(Offer).where(Offer.waitlist_id == b_entry.id)).status == "withdrawn"
    assert _open_offer(svc, C) is not None


def test_nobody_waiting_frees_the_time(svc, full):
    noor, first, _ = full
    booking.cancel(svc, first.id, pseudonym=S[0])
    assert "10:00" in _starts(noor.id)
    assert svc.scalars(select(Offer)).all() == []


def test_too_close_to_the_session_to_offer(svc, full):
    noor, first, _ = full
    waitlist.join(svc, B, noor.id)
    clock.advance(at(9, 52) - clock.now())                     # 8 min before the 10:00 session
    booking.cancel(svc, first.id, pseudonym=S[0])              # hold would be 4 min: not offered
    assert svc.scalars(select(Offer)).all() == []
    assert "10:00" in _starts(noor.id)
    assert waitlist.my_entries(svc, B)[0]["status"] == "waiting"


def test_ageing_moves_old_normal_entries_up(svc, full):
    noor, first, _ = full
    c = waitlist.join(svc, C, noor.id)                         # normal
    clock.advance(timedelta(hours=1))
    waitlist.join(svc, E, noor.id, urgent=True)
    assert waitlist.my_entries(svc, C)[0]["ahead"] == 1
    clock.advance(timedelta(hours=70))
    assert waitlist.age(svc) == 0                              # C has waited 71 h
    clock.advance(timedelta(hours=1))
    assert waitlist.age(svc) == 1                              # 72 h
    assert svc.get(WaitlistEntry, c.id).tier == waitlist.URGENT
    assert waitlist.my_entries(svc, C)[0]["ahead"] == 0         # same join time, so C is first now


def test_ageing_job_runs_on_the_tick_and_rearms(svc, full):
    noor, _, _ = full
    c = waitlist.join(svc, C, noor.id)
    clock.advance(timedelta(hours=73))
    notify.tick(svc)
    assert svc.get(WaitlistEntry, c.id).tier == waitlist.URGENT
    assert notify.cancel_job(waitlist.AGEING_JOB, "all")       # re-armed for the next hour


def test_restart_restores_heaps_holds_and_expiry(svc, full):
    noor, first, _ = full
    line = _plan_line(svc, noor.id)
    waitlist.leave(svc, D, line["D"].id)
    booking.cancel(svc, first.id, pseudonym=S[0])
    order = [waitlist.my_entries(svc, p)[0]["ahead"] for p in (E, C, A)]

    notify.reset()                 # what rebuild_all does on startup
    booking.rebuild(svc)
    waitlist.rebuild(svc)
    notify.rebuild(svc)

    assert [waitlist.my_entries(svc, p)[0]["ahead"] for p in (E, C, A)] == order == [0, 1, 2]
    assert "10:00" not in _starts(noor.id)                     # B's hold survived
    clock.advance(timedelta(minutes=31))
    notify.tick(svc)                                           # expiry job was re-armed
    assert _open_offer(svc, E) is not None
