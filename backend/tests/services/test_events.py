"""Events service: AVL-backed calendar, capacity, FIFO waitlist, reminders, restart safety."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app import clock
from app.models import Notification, Registration
from app.services import events, notify

from .conftest import T0

DAY = timedelta(days=1)
S = [f"{i:x}" * 64 for i in range(1, 8)]  # fake pseudonyms (64 hex chars)


def _make(db, title, day, hour=10, capacity=20, tags=()):
    start = T0 + day * DAY + timedelta(hours=hour - 10)
    return events.create(db, title, start, start + timedelta(hours=1), "Room 1", capacity, list(tags))


def test_range_and_upcoming_are_in_start_order(db):
    _make(db, "Fair", 12)
    _make(db, "Sleep clinic", 3, tags=["Sleep"])
    _make(db, "Yoga", -2)
    _make(db, "Art", 5, tags=["mindfulness", " SLEEP "])
    _make(db, "Peer circle", 8)

    got = events.between(T0 + 3 * DAY - timedelta(hours=1), T0 + 9 * DAY)
    assert [e.title for e in got] == ["Sleep clinic", "Art", "Peer circle"]
    assert [e.title for e in events.between(T0, T0 + 30 * DAY, "sleep")] == ["Sleep clinic", "Art"]
    assert events.get(got[1].id).tags == ("mindfulness", "sleep")
    assert [e.title for e in events.upcoming(2)] == ["Sleep clinic", "Art"]  # Yoga is past
    with pytest.raises(ValueError):
        events.between(T0 + DAY, T0)


def test_same_start_time_does_not_collide(db):
    a = _make(db, "A", 1)
    b = _make(db, "B", 1)
    assert [e.id for e in events.upcoming(5)] == [a.id, b.id]


def test_validation(db):
    with pytest.raises(ValueError):
        events.create(db, "x", T0 + DAY, T0 + DAY, "", 5)
    with pytest.raises(ValueError):
        events.create(db, " ", T0 + DAY, T0 + 2 * DAY, "", 5)
    with pytest.raises(events.EventNotFound):
        events.register(db, 999, S[0])


def test_capacity_then_fifo_waitlist_then_promotion(db, channel):
    ev = _make(db, "Yoga", 2, capacity=2)
    assert [events.register(db, ev.id, s) for s in S[:4]] == ["registered", "registered", "waitlisted", "waitlisted"]
    assert (ev.registered, ev.waitlisted) == (2, 2)
    with pytest.raises(events.RegistrationConflict):
        events.register(db, ev.id, S[2])

    events.unregister(db, ev.id, S[0])
    assert (ev.registered, ev.waitlisted) == (2, 1)
    statuses = events.statuses_for(db, S[2], [ev.id])
    assert statuses.get(ev.id) == "registered"  # head of the queue moved in

    notify.tick(db)
    assert channel.sent == ["You're in: Yoga"]
    with pytest.raises(events.EventNotFound):
        events.unregister(db, ev.id, S[0])


def test_leaving_the_waitlist_and_rejoining_goes_to_the_back(db):
    ev = _make(db, "Talk", 2, capacity=1)
    events.register(db, ev.id, S[0])
    for s in S[1:4]:
        events.register(db, ev.id, s)  # queue: S1, S2, S3
    events.unregister(db, ev.id, S[1])
    events.register(db, ev.id, S[1])   # queue: S2, S3, S1 (S1's old entry is stale)

    order = []
    for _ in range(3):
        current = db.scalar(select(Registration.pseudonym).where(
            Registration.event_id == ev.id, Registration.status == "registered"))
        events.unregister(db, ev.id, current)
        order.append(db.scalar(select(Registration.pseudonym).where(
            Registration.event_id == ev.id, Registration.status == "registered")))
    assert order == [S[2], S[3], S[1]]
    assert ev.waitlisted == 0


def test_registration_closes_when_the_event_starts(db):
    ev = _make(db, "Now", 0, hour=10)
    with pytest.raises(ValueError):
        events.register(db, ev.id, S[0])


def test_event_reminder_fires_one_hour_before(db, channel):
    ev = _make(db, "Mindfulness hour", 1, hour=16)
    events.register(db, ev.id, S[0])
    clock.freeze(ev.start - timedelta(hours=1))
    notify.tick(db)
    assert notify.inbox(db, S[0])[0]["title"] == "Mindfulness hour starts in 1 hour"


def test_unregister_cancels_the_reminder(db, channel):
    ev = _make(db, "Yoga", 1)
    events.register(db, ev.id, S[0])
    events.unregister(db, ev.id, S[0])
    clock.freeze(ev.start)
    notify.tick(db)
    assert channel.sent == []


def test_moving_an_event_moves_it_in_the_tree_and_retimes_reminders(db):
    ev = _make(db, "Workshop", 2)
    other = _make(db, "Other", 4)
    events.register(db, ev.id, S[0])
    new_start = T0 + 6 * DAY
    events.update(db, ev.id, start=new_start, end=new_start + timedelta(hours=2))
    assert [e.id for e in events.upcoming(5)] == [other.id, ev.id]
    pending = db.scalars(select(Notification).where(Notification.status == "pending")).all()
    assert [n.send_at for n in pending] == [new_start - timedelta(hours=1)]
    with pytest.raises(ValueError):
        events.update(db, ev.id, end=new_start - timedelta(hours=1))


def test_bigger_capacity_promotes_from_the_queue(db):
    ev = _make(db, "Yoga", 2, capacity=1)
    for s in S[:4]:
        events.register(db, ev.id, s)
    events.update(db, ev.id, capacity=3, title="Yoga+")
    assert (ev.registered, ev.waitlisted, ev.title) == (3, 1, "Yoga+")
    events.update(db, ev.id, capacity=1)  # shrinking never removes anyone
    assert ev.registered == 3


def test_remove_deletes_everything_and_cancels_reminders(db, channel):
    ev = _make(db, "Gone", 2, capacity=1)
    events.register(db, ev.id, S[0])
    events.register(db, ev.id, S[1])
    events.remove(db, ev.id)
    assert events.upcoming(5) == []
    with pytest.raises(events.EventNotFound):
        events.get(ev.id)
    assert db.scalars(select(Registration)).all() == []
    assert notify.pending_count() == 0


def test_rebuild_answers_identically(db):
    """Plan 12.3 restart safety: rebuild from SQLite, same calendar, same counts, same queue order."""
    a = _make(db, "A", 3, capacity=1, tags=["exams"])
    _make(db, "B", 1)
    for s in S[:4]:
        events.register(db, a.id, s)
    events.unregister(db, a.id, S[2])  # leaves the waitlist: queue S1, S3

    before = [events.to_dict(e) for e in events.between(T0, T0 + 10 * DAY)]
    events.rebuild(db)
    after = [events.to_dict(e) for e in events.between(T0, T0 + 10 * DAY)]
    assert before == after

    events.unregister(db, a.id, S[0])
    assert events.statuses_for(db, S[1], [a.id]).get(a.id) == "registered"
    events.register(db, a.id, S[5])  # new positions continue after the old ones
    events.unregister(db, a.id, S[1])
    assert events.statuses_for(db, S[3], [a.id]).get(a.id) == "registered"
