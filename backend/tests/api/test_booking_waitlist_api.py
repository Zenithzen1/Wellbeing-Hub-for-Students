"""API tests for /counsellors, /bookings, /counsellor/*, /waitlist and /offers.

Auth is Rithwik's and not built yet, so get_current_user is overridden: the X-Test-User header picks the caller.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import Request
from sqlalchemy import func, select

from app import clock, db
from app.deps import CurrentUser, get_current_user
from app.models import Booking
from app.services import booking, notify

T0 = datetime(2026, 11, 30, 6, 0, tzinfo=timezone.utc)  # Mon 30 Nov, 10:00 Dubai
USERS = {
    "s1": CurrentUser(1, "S", "a" * 64),
    "s2": CurrentUser(2, "S", "b" * 64),
    "noor": CurrentUser(3, "C"),
    "mehta": CurrentUser(6, "C"),
    "nobody": CurrentUser(7, "C"),  # counsellor account without a profile
    "admin": CurrentUser(4, "A"),
}
USERS.update({f"x{i}": CurrentUser(100 + i, "S", f"{i:064x}") for i in range(50)})


def at(h, m=0, day=1):
    return datetime(2026, 12, day, h, m, tzinfo=clock.DUBAI).isoformat()


@pytest.fixture
def api(client, monkeypatch):
    """client plus .as_(name); Dr Noor (account 3) and Dr Mehta (account 6) exist; clock frozen at T0."""
    from app.main import app

    def fake_user(request: Request) -> CurrentUser:
        return USERS[request.headers.get("x-test-user", "s1")]

    app.dependency_overrides[get_current_user] = fake_user
    monkeypatch.setattr(notify, "CHANNELS", [])
    clock.freeze(T0)
    session = db.SessionLocal()
    try:
        client.noor = booking.add_counsellor(session, 3, "Dr Noor", ["anxiety"]).id
        client.mehta = booking.add_counsellor(session, 6, "Dr Mehta", ["study"]).id
    finally:
        session.close()

    def as_(name):
        client.headers["x-test-user"] = name
        return client

    client.as_ = as_
    yield client
    app.dependency_overrides.clear()
    clock.unfreeze()


def _window(api, start, end, kind="open", who="noor"):
    r = api.as_(who).post("/api/counsellor/availability", json={"start": start, "end": end, "kind": kind})
    assert r.status_code == 201, r.text
    return r.json()


def _book(api, who, start, cid=None, **extra):
    return api.as_(who).post("/api/bookings", json={"counsellor_id": cid or api.noor, "start": start,
                                                     "reason": "anxiety", **extra})


def test_counsellors_and_free_grid(api):
    _window(api, at(9), at(12))
    _window(api, at(10), at(10, 30), kind="blocked")
    r = api.as_("s1").get("/api/counsellors")
    assert [c["display_name"] for c in r.json()] == ["Dr Mehta", "Dr Noor"]

    r = api.get(f"/api/counsellors/{api.noor}/free", params={"date": "2026-12-01", "days": 2})
    assert r.status_code == 200
    tue, wed = r.json()
    assert tue["day"] == "2026-12-01" and wed["starts"] == []
    local = [clock.to_local(datetime.fromisoformat(t)).strftime("%H:%M") for t in tue["starts"]]
    assert local == ["09:00", "09:15", "10:30", "10:45", "11:00", "11:15"]
    r = api.get(f"/api/counsellors/{api.noor}/free", params={"date": "2026-12-01", "first_visit": True})
    assert len(r.json()[0]["starts"]) == 4
    assert api.get("/api/counsellors/999/free").status_code == 404
    assert api.get(f"/api/counsellors/{api.noor}/free", params={"days": 8}).status_code == 422


def test_book_view_cancel(api):
    _window(api, at(9), at(17))
    r = _book(api, "s1", at(10), first_visit=True)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["counsellor_name"] == "Dr Noor" and b["status"] == "active"
    assert datetime.fromisoformat(b["end"]) - datetime.fromisoformat(b["start"]) == timedelta(minutes=60)

    assert _book(api, "s2", at(10, 30)).status_code == 409
    assert _book(api, "s2", at(10, 10)).status_code == 400
    assert _book(api, "s2", at(8)).status_code == 400
    assert _book(api, "s2", at(12), cid=999).status_code == 404
    bad = api.as_("s2").post("/api/bookings", json={"counsellor_id": api.noor, "start": at(12), "reason": "x"})
    assert bad.status_code == 422
    assert _book(api, "noor", at(12)).status_code == 403          # counsellors don't book

    assert [x["id"] for x in api.as_("s1").get("/api/bookings/me").json()] == [b["id"]]
    assert api.as_("s2").get("/api/bookings/me").json() == []

    sessions = api.as_("noor").get("/api/counsellor/sessions", params={"date": "2026-12-01"}).json()
    assert [(s["student"], s["reason"], s["identity"]) for s in sessions] == [("#AAAAAA", "anxiety", None)]
    assert api.as_("mehta").get("/api/counsellor/sessions", params={"date": "2026-12-01"}).json() == []
    assert api.as_("nobody").get("/api/counsellor/sessions").status_code == 403
    assert api.as_("noor").patch(f"/api/bookings/{b['id']}", json={"status": "completed"}).status_code == 400

    assert api.as_("s2").delete(f"/api/bookings/{b['id']}").status_code == 404     # not yours
    assert api.as_("mehta").delete(f"/api/bookings/{b['id']}").status_code == 404
    assert api.as_("s1").delete(f"/api/bookings/{b['id']}").status_code == 204
    assert api.as_("s1").delete(f"/api/bookings/{b['id']}").status_code == 400     # already cancelled
    assert _book(api, "s2", at(10, 30)).status_code == 201


def test_counsellor_availability(api):
    w = _window(api, at(9), at(12))
    assert api.as_("noor").post("/api/counsellor/availability",
                                json={"start": at(11), "end": at(13)}).status_code == 409
    assert api.post("/api/counsellor/availability", json={"start": at(13), "end": at(12)}).status_code == 400
    assert api.post("/api/counsellor/availability", json={"start": "2026-12-01T13:00:00",
                                                          "end": at(14)}).status_code == 422  # no offset
    listed = api.get("/api/counsellor/availability", params={"from": at(0), "to": at(23)}).json()
    assert [x["id"] for x in listed] == [w["id"]]
    _book(api, "s1", at(9))
    assert api.as_("noor").delete(f"/api/counsellor/availability/{w['id']}").status_code == 409
    assert api.as_("mehta").delete(f"/api/counsellor/availability/{w['id']}").status_code == 404
    assert api.as_("admin").post("/api/counsellor/availability",
                                 json={"start": at(13), "end": at(14)}).status_code == 403


def test_waitlist_offer_accept(api):
    _window(api, at(10), at(10, 45))
    first = _book(api, "s1", at(10)).json()

    r = api.as_("s2").post("/api/waitlist", json={"counsellor_id": api.noor, "urgent": True})
    assert r.status_code == 201, r.text
    assert (r.json()["ahead"], r.json()["urgent"], r.json()["offer"]) == (0, True, None)
    assert api.post("/api/waitlist", json={"counsellor_id": api.noor}).status_code == 409
    assert api.post("/api/waitlist", json={"counsellor_id": 999}).status_code == 404
    assert api.post("/api/waitlist", json={}).status_code == 201                    # "any counsellor"
    assert api.as_("noor").get("/api/counsellor/waitlist").json() == \
        {"urgent": 1, "normal": 0, "any_urgent": 0, "any_normal": 1}

    assert api.as_("s1").delete(f"/api/bookings/{first['id']}").status_code == 204
    entries = api.as_("s2").get("/api/waitlist").json()
    offer = next(e["offer"] for e in entries if e["offer"])
    assert offer["start"] == first["start"] and offer["counsellor_name"] == "Dr Noor"
    assert _book(api, "x0", at(10)).status_code == 409                               # held for s2

    assert api.as_("s1").post(f"/api/offers/{offer['id']}/accept").status_code == 404
    r = api.as_("s2").post(f"/api/offers/{offer['id']}/accept", json={"reason": "sleep"})
    assert r.status_code == 201, r.text
    assert r.json()["reason"] == "sleep" and r.json()["start"] == first["start"]
    assert api.get("/api/waitlist").json() == []                                     # left the "any" line too
    assert api.post(f"/api/offers/{offer['id']}/accept").status_code == 409
    assert api.post(f"/api/offers/{offer['id']}/decline").status_code == 409


def test_waitlist_decline_and_leave(api):
    _window(api, at(10), at(10, 45))
    first = _book(api, "s1", at(10)).json()
    entry = api.as_("s2").post("/api/waitlist", json={"counsellor_id": api.noor}).json()
    assert api.as_("x1").delete(f"/api/waitlist/{entry['id']}").status_code == 404
    api.as_("s1").delete(f"/api/bookings/{first['id']}")
    offer = api.as_("s2").get("/api/waitlist").json()[0]["offer"]
    assert api.post(f"/api/offers/{offer['id']}/decline").status_code == 204
    assert api.get("/api/waitlist").json() == []
    assert api.post("/api/offers/999/decline").status_code == 404
    assert api.delete(f"/api/waitlist/{entry['id']}").status_code == 404


def test_fifty_students_one_slot(api):
    """No double booking: 50 concurrent POST /bookings for the same slot -> one 201, 49 x 409, one row."""
    from app.main import app

    _window(api, at(10), at(11))

    async def race():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            return await asyncio.gather(*[
                ac.post("/api/bookings", headers={"x-test-user": f"x{i}"},
                        json={"counsellor_id": api.noor, "start": at(10), "reason": "other"})
                for i in range(50)])

    codes = sorted(r.status_code for r in asyncio.run(race()))
    assert codes == [201] + [409] * 49
    session = db.SessionLocal()
    try:
        assert session.scalar(select(func.count()).select_from(Booking).where(Booking.status == "active")) == 1
    finally:
        session.close()
