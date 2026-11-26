"""Notify service: timed heap -> FIFO queue, retries, dead letters, restart safety, jobs, inbox, SSE."""

import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import clock
from app.models import Notification
from app.services import notify

from .conftest import T0

STUDENT = "a" * 64
OTHER = "b" * 64


def _status(db, nid):
    db.expire_all()
    return db.get(Notification, nid).status


def test_session_reminders_fire_at_t_minus_24h_and_cancel_drops_the_rest(db, channel):
    """Plan 12.3: advance to T-24h, one tick, one inbox item; cancel, and T-1h never fires."""
    start = T0 + timedelta(days=2)
    rows = notify.schedule_session_reminders(db, 7, STUDENT, start)
    assert [r.send_at for r in rows] == [start - timedelta(hours=24), start - timedelta(hours=1)]

    notify.tick(db)
    assert notify.inbox(db, STUDENT) == []

    clock.freeze(start - timedelta(hours=24))
    notify.tick(db)
    inbox = notify.inbox(db, STUDENT)
    assert [n["title"] for n in inbox] == ["Session in 24 hours"]

    assert notify.cancel_session_reminders(db, 7) == 1
    assert notify.pending_count() == 0
    clock.freeze(start - timedelta(hours=1))
    notify.tick(db)
    assert len(notify.inbox(db, STUDENT)) == 1
    assert _status(db, rows[1].id) == "cancelled"


def test_session_reminders_skip_times_already_past(db):
    start = T0 + timedelta(hours=3)
    rows = notify.schedule_session_reminders(db, 8, STUDENT, start)
    assert [r.send_at for r in rows] == [start - timedelta(hours=1)]  # the T-24h one is already past


def test_tick_worked_example(db, channel):
    """Plan 7.1: r1, r2 due at 09:00, r3 at 10:00. r2's email fails and is retried at +1 min."""
    nine = T0
    r1 = notify.schedule(db, STUDENT, "announcement", {"title": "r1"}, nine)
    r2 = notify.schedule(db, STUDENT, "announcement", {"title": "r2"}, nine)
    r3 = notify.schedule(db, STUDENT, "announcement", {"title": "r3"}, nine + timedelta(hours=1))
    channel.fail_for = {"r2"}

    notify.tick(db)
    assert channel.sent == ["r1"]
    assert _status(db, r1.id) == "sent" and _status(db, r3.id) == "pending"
    db.expire_all()
    row2 = db.get(Notification, r2.id)
    assert row2.status == "pending" and row2.attempts == 1 and row2.send_at == nine + timedelta(minutes=1)

    channel.fail_for = set()
    clock.advance(timedelta(minutes=1))
    notify.tick(db)
    assert channel.sent == ["r1", "r2"]


def test_due_items_are_delivered_first_in_first_out(db, channel):
    for i in range(5):
        notify.schedule(db, STUDENT, "announcement", {"title": f"m{i}"}, T0 - timedelta(minutes=10 - i))
    notify.tick(db)
    assert channel.sent == ["m0", "m1", "m2", "m3", "m4"]


def test_fourth_failure_goes_to_dead_letters(db, channel):
    row = notify.send_now(db, STUDENT, "announcement", {"title": "bad"})
    channel.fail_for = {"bad"}
    waits = []
    for _ in range(notify.MAX_ATTEMPTS):
        notify.tick(db)
        db.expire_all()
        current = db.get(Notification, row.id)
        if current.status == "pending":
            waits.append(current.send_at - clock.now())
            clock.freeze(current.send_at)
    assert waits == list(notify.BACKOFF)
    assert _status(db, row.id) == "dead"
    dead = notify.dead_letters(db)
    assert len(dead) == 1 and dead[0]["attempts"] == 4 and "smtp down" in dead[0]["last_error"]
    assert "recipient" not in dead[0]
    assert notify.inbox(db, STUDENT) == []


def test_restart_sends_slightly_late_and_skips_very_late(db, channel):
    late = notify.schedule(db, STUDENT, "announcement", {"title": "late"}, T0 + timedelta(minutes=10))
    stale = notify.schedule(db, STUDENT, "announcement", {"title": "stale"}, T0 + timedelta(minutes=5))
    future = notify.schedule(db, STUDENT, "announcement", {"title": "future"}, T0 + timedelta(hours=3))

    clock.freeze(T0 + timedelta(minutes=50))  # "server was off": nothing ticked
    notify.reset()
    clock.freeze(T0 + timedelta(hours=1, minutes=7))
    notify.rebuild(db)
    assert _status(db, stale.id) == "skipped" and _status(db, late.id) == "pending"
    assert notify.pending_count() == 2

    notify.tick(db)
    assert channel.sent == ["late"]
    assert _status(db, future.id) == "pending"


def test_rebuild_gives_the_same_heap_order(db, channel):
    for minutes in (30, 10, 20):
        notify.schedule(db, STUDENT, "announcement", {"title": str(minutes)}, T0 + timedelta(minutes=minutes))
    notify.reset()
    notify.rebuild(db)
    clock.advance(timedelta(hours=1))
    notify.tick(db)
    assert channel.sent == ["10", "20", "30"]


def test_jobs_run_once_can_move_and_cancel(db):
    calls = []
    notify.register_job("test_job", lambda session, ref: calls.append((ref, clock.now())))
    notify.schedule_job("test_job", "a", T0 + timedelta(minutes=5))
    notify.schedule_job("test_job", "b", T0 + timedelta(minutes=5))
    notify.schedule_job("test_job", "a", T0 + timedelta(minutes=20))  # moved
    assert notify.cancel_job("test_job", "b") and not notify.cancel_job("test_job", "b")

    clock.advance(timedelta(minutes=10))
    notify.tick(db)
    assert calls == []
    clock.advance(timedelta(minutes=10))
    notify.tick(db)
    notify.tick(db)
    assert [ref for ref, _ in calls] == ["a"]
    assert db.scalars(select(Notification)).all() == []  # jobs never reach the delivery queue


def test_failing_job_does_not_stop_the_tick(db, channel):
    def boom(session, ref):
        raise RuntimeError("bug")

    notify.register_job("boom", boom)
    notify.schedule_job("boom", "x", T0)
    notify.send_now(db, STUDENT, "announcement", {"title": "still sent"})
    notify.tick(db)
    assert channel.sent == ["still sent"]


def test_announcements_reach_everyone_and_reads_are_per_person(db, channel):
    ann = notify.announce(db, "Wellness week", "Free yoga all week")
    personal = notify.send_now(db, OTHER, "event_promoted", {"title": "You're in"})
    notify.tick(db)

    mine = notify.inbox(db, STUDENT)
    assert [n["title"] for n in mine] == ["Wellness week"] and not mine[0]["read"]
    assert {n["title"] for n in notify.inbox(db, OTHER)} == {"Wellness week", "You're in"}

    notify.mark_read(db, STUDENT, ann.id)
    notify.mark_read(db, STUDENT, ann.id)  # idempotent
    assert notify.inbox(db, STUDENT)[0]["read"]
    assert not next(n for n in notify.inbox(db, OTHER) if n["id"] == ann.id)["read"]
    with pytest.raises(KeyError):
        notify.mark_read(db, STUDENT, personal.id)  # not mine
    with pytest.raises(KeyError):
        notify.mark_read(db, STUDENT, 999)


def test_scheduled_announcement_waits_for_its_time(db, channel):
    notify.announce(db, "Later", "", T0 + timedelta(hours=2))
    notify.tick(db)
    assert channel.sent == []
    clock.advance(timedelta(hours=2))
    notify.tick(db)
    assert channel.sent == ["Later"]


def test_delivery_pushes_to_open_tabs(db, channel):
    async def scenario():
        mine = notify.subscribe((STUDENT, notify.BROADCAST))
        theirs = notify.subscribe((OTHER, notify.BROADCAST))
        try:
            notify.schedule_session_reminders(db, 1, STUDENT, T0 + timedelta(minutes=61))
            clock.advance(timedelta(minutes=1))
            notify.tick(db)
            notify.publish(notify.BROADCAST, "slot_taken", {"counsellor_id": 3})
            first = await asyncio.wait_for(mine.queue.get(), 1)
            second = await asyncio.wait_for(mine.queue.get(), 1)
            other = await asyncio.wait_for(theirs.queue.get(), 1)
            return first, second, other, theirs.queue.empty()
        finally:
            notify.unsubscribe(mine)
            notify.unsubscribe(theirs)

    (ev1, data1), second, other, nothing_else = asyncio.run(scenario())
    assert ev1 == "reminder" and data1["title"] == "Session in 1 hour"
    assert second == ("slot_taken", {"counsellor_id": 3})
    assert other == ("slot_taken", {"counsellor_id": 3}) and nothing_else
    assert notify.format_sse(ev1, data1).startswith("event: reminder\ndata: {")
