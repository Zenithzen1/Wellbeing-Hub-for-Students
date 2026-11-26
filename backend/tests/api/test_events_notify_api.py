"""API tests for /events, /notifications, /admin/announcements, /admin/dead-letters.

Auth is Rithwik's and not built yet, so get_current_user is overridden with a test user.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import clock, db
from app.deps import CurrentUser, get_current_user
from app.services import notify

T0 = datetime(2026, 11, 30, 6, 0, tzinfo=timezone.utc)
STUDENT = CurrentUser(1, "S", "a" * 64)
STUDENT2 = CurrentUser(2, "S", "b" * 64)
COUNSELLOR = CurrentUser(3, "C")
ADMIN = CurrentUser(4, "A")
CUSTODIAN = CurrentUser(5, "K")


@pytest.fixture
def api(client, monkeypatch):
    """client plus .as_(user) to pick who is calling; the clock is frozen at T0."""
    from app.main import app

    current = {"user": STUDENT}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    monkeypatch.setattr(notify, "CHANNELS", [])
    clock.freeze(T0)

    def as_(user):
        current["user"] = user
        return client

    client.as_ = as_
    yield client
    app.dependency_overrides.clear()
    clock.unfreeze()


def _iso(dt):
    return dt.isoformat()


def _event(api, title="Yoga", days=2, capacity=20, tags=("sleep",)):
    start = T0 + timedelta(days=days)
    r = api.as_(ADMIN).post("/api/events", json={"title": title, "start": _iso(start),
                                                  "end": _iso(start + timedelta(hours=1)),
                                                  "location": "Hall", "capacity": capacity, "tags": list(tags)})
    assert r.status_code == 201, r.text
    return r.json()


def _tick():
    session = db.SessionLocal()
    try:
        notify.tick(session)
    finally:
        session.close()


def test_event_crud_and_queries(api):
    ev = _event(api, "Sleep clinic", days=3)
    _event(api, "Fair", days=12, tags=())
    assert ev["spots_left"] == 20 and ev["tags"] == ["sleep"] and ev["my_status"] is None

    r = api.as_(STUDENT).get("/api/events", params={"from": _iso(T0), "to": _iso(T0 + timedelta(days=9))})
    assert [e["title"] for e in r.json()] == ["Sleep clinic"]
    r = api.get("/api/events", params={"from": _iso(T0), "to": _iso(T0 + timedelta(days=30)), "tag": "Sleep"})
    assert [e["title"] for e in r.json()] == ["Sleep clinic"]
    assert [e["title"] for e in api.get("/api/events").json()] == ["Sleep clinic", "Fair"]
    assert [e["title"] for e in api.get("/api/events/upcoming", params={"k": 1}).json()] == ["Sleep clinic"]
    assert api.get("/api/events", params={"from": _iso(T0), "to": _iso(T0 - timedelta(days=1))}).status_code == 400

    r = api.as_(ADMIN).patch(f"/api/events/{ev['id']}", json={"title": "Sleep clinic II", "capacity": 5})
    assert r.status_code == 200 and r.json()["title"] == "Sleep clinic II" and r.json()["capacity"] == 5
    assert api.patch("/api/events/999", json={"title": "x"}).status_code == 404
    assert api.patch(f"/api/events/{ev['id']}", json={"end": _iso(T0)}).status_code == 400

    assert api.delete(f"/api/events/{ev['id']}").status_code == 204
    assert api.delete(f"/api/events/{ev['id']}").status_code == 404
    assert [e["title"] for e in api.get("/api/events").json()] == ["Fair"]


def test_times_without_offset_are_rejected(api):
    r = api.as_(ADMIN).post("/api/events", json={"title": "x", "start": "2026-12-01T10:00:00",
                                                  "end": "2026-12-01T11:00:00", "capacity": 5})
    assert r.status_code == 422


def test_register_waitlist_and_unregister(api):
    ev = _event(api, capacity=1)
    url = f"/api/events/{ev['id']}/register"
    r = api.as_(STUDENT).post(url)
    assert r.status_code == 201 and r.json() == {"event_id": ev["id"], "status": "registered"}
    assert api.post(url).status_code == 409
    assert api.get("/api/events/upcoming").json()[0]["my_status"] == "registered"

    assert api.as_(STUDENT2).post(url).json()["status"] == "waitlisted"
    assert api.as_(STUDENT).delete(url).status_code == 204
    assert api.delete(url).status_code == 404
    assert api.as_(STUDENT2).get("/api/events/upcoming").json()[0]["my_status"] == "registered"

    _tick()
    inbox = api.get("/api/notifications").json()
    assert [n["kind"] for n in inbox] == ["event_promoted"]
    assert api.post("/api/events/999/register").status_code == 404


def test_role_checks(api):
    ev = _event(api)
    url = f"/api/events/{ev['id']}"
    body = {"title": "x", "start": _iso(T0 + timedelta(days=1)), "end": _iso(T0 + timedelta(days=1, hours=1)),
            "capacity": 3}
    for user in (STUDENT, COUNSELLOR, CUSTODIAN):
        api.as_(user)
        assert api.post("/api/events", json=body).status_code == 403
        assert api.patch(url, json={"title": "y"}).status_code == 403
        assert api.delete(url).status_code == 403
        assert api.post("/api/admin/announcements", json={"title": "x"}).status_code == 403
        assert api.get("/api/admin/dead-letters").status_code == 403
    for user in (COUNSELLOR, ADMIN, CUSTODIAN):
        assert api.as_(user).post(f"{url}/register").status_code == 403
    for user in (ADMIN, CUSTODIAN):
        api.as_(user)
        assert api.get("/api/notifications").status_code == 403
        assert api.post("/api/notifications/1/read").status_code == 403
        assert api.get("/api/stream").status_code == 403
    for user in (STUDENT, COUNSELLOR, ADMIN, CUSTODIAN):
        assert api.as_(user).get("/api/events").status_code == 200


def test_announcement_inbox_and_read(api):
    r = api.as_(ADMIN).post("/api/admin/announcements", json={"title": "Wellness week", "body": "Yoga daily"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    later = api.post("/api/admin/announcements",
                     json={"title": "Later", "send_at": _iso(T0 + timedelta(hours=2))}).json()
    _tick()

    for user in (STUDENT, COUNSELLOR):
        inbox = api.as_(user).get("/api/notifications").json()
        assert [n["title"] for n in inbox] == ["Wellness week"] and inbox[0]["read"] is False
    nid = inbox[0]["id"]
    assert api.as_(STUDENT).post(f"/api/notifications/{nid}/read").status_code == 204
    assert api.get("/api/notifications").json()[0]["read"] is True
    assert api.as_(COUNSELLOR).get("/api/notifications").json()[0]["read"] is False
    assert api.post(f"/api/notifications/{later['id']}/read").status_code == 404  # not delivered yet
    assert api.post("/api/notifications/999/read").status_code == 404


def test_dead_letters(api, monkeypatch):
    def down(row):
        raise ConnectionError("smtp down")

    monkeypatch.setattr(notify, "CHANNELS", [down])
    api.as_(ADMIN).post("/api/admin/announcements", json={"title": "Doomed"})
    for _ in range(notify.MAX_ATTEMPTS):
        _tick()
        clock.advance(timedelta(minutes=30))
    dead = api.get("/api/admin/dead-letters").json()
    assert [(d["title"], d["attempts"]) for d in dead] == [("Doomed", 4)]
