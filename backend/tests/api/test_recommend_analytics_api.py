"""API tests for /resources, /tags, /me/interests, /engagements, /recommendations and /analytics/*."""

from datetime import datetime, timedelta, timezone

import pytest

from app import clock
from app.deps import CurrentUser, get_current_user
from app.services import notify

T0 = datetime(2026, 11, 30, 6, 0, tzinfo=timezone.utc)
STUDENT = CurrentUser(1, "S", "a" * 64)
COUNSELLOR = CurrentUser(3, "C")
ADMIN = CurrentUser(4, "A")


@pytest.fixture
def api(client, monkeypatch):
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


def test_resources_interests_and_recommendations(api):
    r = api.as_(ADMIN).post("/api/resources", json={"title": "Breathing audio", "kind": "audio",
                                                     "url": "https://example.org/b", "tags": ["Exams"]})
    assert r.status_code == 201 and r.json()["tags"] == ["exams"] and r.json()["item"].startswith("r:")
    item = r.json()["item"]
    start = T0 + timedelta(days=2)
    ev = api.post("/api/events", json={"title": "Exam-stress workshop", "start": start.isoformat(),
                                       "end": (start + timedelta(hours=1)).isoformat(), "capacity": 20,
                                       "tags": ["exams"]}).json()
    assert api.post("/api/resources", json={"title": "x", "kind": "audio", "url": "ftp://x"}).status_code == 400
    assert api.as_(STUDENT).post("/api/resources", json={"title": "x", "kind": "audio",
                                                         "url": "https://x"}).status_code == 403

    assert api.get("/api/tags").json() == ["exams"]
    out = api.get("/api/recommendations").json()
    assert out["cold_start"] is True and [i["title"] for i in out["items"]] == ["Exam-stress workshop",
                                                                                 "Breathing audio"]

    assert api.put("/api/me/interests", json={"tags": ["unknown"]}).status_code == 400
    assert api.put("/api/me/interests", json={"tags": ["Exams"]}).json() == ["exams"]
    assert api.get("/api/me/interests").json() == ["exams"]
    out = api.get("/api/recommendations", params={"k": 5}).json()
    assert out["cold_start"] is False
    assert [(i["item"], i["reason"]) for i in out["items"]] == [(f"e:{ev['id']}", "Matches your interest: Exams"),
                                                                (item, "Matches your interest: Exams")]

    assert api.post("/api/engagements", json={"item": item, "kind": "saved"}).status_code == 201
    assert api.post("/api/engagements", json={"item": item, "kind": "saved"}).status_code == 200
    assert api.post("/api/engagements", json={"item": "r:999", "kind": "saved"}).status_code == 404
    assert api.post("/api/engagements", json={"item": "x:1", "kind": "saved"}).status_code == 422
    assert api.get("/api/resources").json()[0]["my"] == ["saved"]
    assert [i["item"] for i in api.get("/api/recommendations").json()["items"]] == [f"e:{ev['id']}"]

    assert api.as_(COUNSELLOR).put("/api/me/interests", json={"tags": []}).status_code == 403
    assert api.get("/api/recommendations").status_code == 403
    assert api.get("/api/resources", params={"tag": "exams"}).json()[0]["my"] == []


def test_analytics_endpoints(api):
    assert api.as_(STUDENT).get("/api/analytics/summary").status_code == 403
    assert api.as_(COUNSELLOR).get("/api/analytics/export.csv").status_code == 403

    r = api.as_(ADMIN).get("/api/analytics/summary", params={"from": "2026-11-18", "to": "2026-11-25"})
    assert r.status_code == 200
    body = r.json()
    assert body["k"] == 5 and body["weeks"] == ["2026-W47", "2026-W48"] and body["first_day"] == "2026-11-16"
    assert api.get("/api/analytics/summary", params={"from": "2026-11-25", "to": "2026-11-18"}).status_code == 400

    r = api.get("/api/analytics/export.csv", params={"from": "2026-11-18", "to": "2026-11-25"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.text.splitlines()[0] == "metric,row,column,value"
