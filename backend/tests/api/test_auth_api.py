"""API tests for /auth/*, /me, opt-in reveal, /custodian/reveal and /audit, through the real session cookie."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app import auth, clock, db
from app.config import settings
from app.db import Base
from app.services import booking, identity, notify

T0 = datetime(2026, 11, 30, 6, 0, tzinfo=timezone.utc)  # Mon 30 Nov, 10:00 Dubai
PW = "correct horse battery"
STUDENT = "25a1cseb0101@uni.ac.ae"
REASON = "Counsellor reported an immediate safety risk"


def at(h, m=0, day=1):
    return datetime(2026, 12, day, h, m, tzinfo=clock.DUBAI).isoformat()


@pytest.fixture
def api(client, monkeypatch):
    """Real auth. Staff: noor@ (counsellor with a profile), admin@, keeper@ (custodian)."""
    public, private = auth.generate_vault_keys()
    monkeypatch.setattr(settings, "vault_public_key", public)
    monkeypatch.setattr(notify, "CHANNELS", [])
    clock.freeze(T0)
    session = db.SessionLocal()
    try:
        noor = identity.create_staff(session, "noor@uni.ac.ae", PW, "C", "Dr Noor")
        booking.add_counsellor(session, noor.id, "Dr Noor", ["anxiety"])
        identity.create_staff(session, "admin@uni.ac.ae", PW, "A", "Wellbeing team")
        identity.create_staff(session, "keeper@uni.ac.ae", PW, "K", "Ms Keeper")
    finally:
        session.close()

    def login(email, password=PW):
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()

    client.login = login
    client.private = private
    yield client
    clock.unfreeze()


def test_register_login_me_logout(api):
    r = api.post("/api/auth/register", json={"email": STUDENT.upper(), "password": PW, "name": "Asha"})
    assert r.status_code == 201, r.text
    me = r.json()
    pse = auth.pseudonym_for(STUDENT)
    assert me["role"] == "S" and me["pseudonym"] == pse and me["display_name"] == f"Student {me['tag']}"

    assert api.post("/api/auth/register", json={"email": STUDENT, "password": PW}).status_code == 409
    assert api.post("/api/auth/register", json={"email": "nope", "password": PW}).status_code == 400
    assert api.post("/api/auth/register", json={"email": "x@uni.ac.ae", "password": "short"}).status_code == 422
    assert api.get("/api/me").status_code == 401
    assert api.post("/api/auth/login", json={"email": STUDENT, "password": "wrong password"}).status_code == 401
    assert api.post("/api/auth/login", json={"email": "who@uni.ac.ae", "password": PW}).status_code == 401

    r = api.post("/api/auth/login", json={"email": STUDENT, "password": PW})
    cookie = r.headers["set-cookie"].lower()
    assert r.status_code == 200 and "httponly" in cookie and "samesite=lax" in cookie
    assert api.get("/api/me").json()["pseudonym"] == pse
    token = api.cookies.get(auth.COOKIE)

    assert api.post("/api/auth/logout").status_code == 204
    api.cookies.clear()
    assert api.get("/api/me").status_code == 401
    assert api.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json()["role"] == "S"
    assert api.get("/api/me", headers={"Authorization": f"Bearer {token}x"}).status_code == 401


def test_roles_come_from_the_token(api):
    api.post("/api/auth/register", json={"email": STUDENT, "password": PW})
    api.login(STUDENT)
    assert api.get("/api/analytics/summary").status_code == 403
    assert api.get("/api/audit").status_code == 403
    assert api.get("/api/bookings/me").status_code == 200

    me = api.login("noor@uni.ac.ae")
    assert me["role"] == "C" and me["display_name"] == "Dr Noor" and me["counsellor_id"] is not None
    assert api.get("/api/bookings/me").status_code == 403

    assert api.login("admin@uni.ac.ae")["role"] == "A"
    assert api.get("/api/analytics/summary").status_code == 200


def test_opt_in_reveal_reaches_only_that_counsellor(api):
    api.login("noor@uni.ac.ae")
    assert api.post("/api/counsellor/availability", json={"start": at(9), "end": at(12)}).status_code == 201

    api.post("/api/auth/register", json={"email": STUDENT, "password": PW, "name": "Asha"})
    api.login(STUDENT)
    cid = api.get("/api/counsellors").json()[0]["id"]
    r = api.post("/api/bookings", json={"counsellor_id": cid, "start": at(9), "reason": "anxiety", "reveal": True})
    assert r.status_code == 201, r.text
    assert api.post("/api/bookings", json={"counsellor_id": cid, "start": at(10),
                                           "reason": "sleep"}).status_code == 201

    api.login("noor@uni.ac.ae")
    sessions = api.get("/api/counsellor/sessions", params={"date": "2026-12-01"}).json()
    tag = auth.display_tag(auth.pseudonym_for(STUDENT))
    assert [(s["student"], s["revealed"], s["identity"]) for s in sessions] == [
        (tag, True, f"Asha <{STUDENT}>"), (tag, False, None)]


def test_break_glass(api):
    api.post("/api/auth/register", json={"email": STUDENT, "password": PW})
    tag = auth.display_tag(auth.pseudonym_for(STUDENT))
    body = {"target": tag, "reason": REASON, "private_key": api.private}

    api.login(STUDENT)
    assert api.post("/api/custodian/reveal", json=body).status_code == 403
    api.login("admin@uni.ac.ae")
    assert api.post("/api/custodian/reveal", json=body).status_code == 403

    api.login("keeper@uni.ac.ae")
    _, wrong = auth.generate_vault_keys()
    assert api.post("/api/custodian/reveal", json={**body, "private_key": wrong}).status_code == 400
    assert api.post("/api/custodian/reveal", json={**body, "reason": "because"}).status_code == 422
    assert api.post("/api/custodian/reveal", json={**body, "target": "#ABCDEF"}).status_code == 404
    r = api.post("/api/custodian/reveal", json=body)
    assert r.status_code == 200 and r.json()["email"] == STUDENT

    api.login("admin@uni.ac.ae")  # every reveal is visible to the department
    log = api.get("/api/audit").json()
    assert [e["action"] for e in log] == ["break_glass_revealed", "break_glass", "break_glass_failed", "break_glass",
                                          "break_glass_failed", "break_glass"]
    assert log[1]["reason"] == REASON and log[1]["actor"] == "Ms Keeper"
    assert all(api.private not in str(e) for e in log)


def test_email_is_stored_only_in_accounts(api):
    """Plan 12.3: a fresh database holds each email in `accounts` only (the vault and reveals are encrypted)."""
    api.login("noor@uni.ac.ae")
    api.post("/api/counsellor/availability", json={"start": at(9), "end": at(12)})
    api.post("/api/auth/register", json={"email": STUDENT, "password": PW, "name": "Asha"})
    api.login(STUDENT)
    cid = api.get("/api/counsellors").json()[0]["id"]
    api.post("/api/bookings", json={"counsellor_id": cid, "start": at(9), "reason": "anxiety", "reveal": True})
    session = db.SessionLocal()
    try:
        for table in Base.metadata.sorted_tables:
            if table.name == "accounts":
                continue
            for row in session.execute(select(table)):
                assert STUDENT not in str(tuple(row)).lower(), table.name
    finally:
        session.close()
