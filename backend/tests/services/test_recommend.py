"""Recommendations: the plan's worked example (section 8.2), the support rule, and keeping in step."""

from datetime import timedelta

import pytest

from app import clock
from app.services import events, recommend
from tests.services.conftest import T0

S1, S2, S3, S4, S5, NEW = (f"{i:x}" * 64 for i in range(1, 7))


@pytest.fixture
def world(db):
    """Section 8.2: S1 picked Exams and saved a sleep item (Sleep 0.5); S2 is on Exams and went to W2;
    S3 is on Sleep and saved R1."""
    recommend.rebuild(db)
    r1 = recommend.create_resource(db, "Sleep-hygiene guide", "article", "https://x/r1", ["Sleep"])
    r2 = recommend.create_resource(db, "Breathing audio", "audio", "https://x/r2", ["Exams"])
    diary = recommend.create_resource(db, "Sleep diary", "article", "https://x/d", ["sleep"])
    w1 = events.create(db, "Exam-stress workshop", T0 + timedelta(days=1), T0 + timedelta(days=1, hours=1),
                       capacity=30, tags=["exams"])
    w2 = events.create(db, "Mindfulness hour", T0 + timedelta(days=3), T0 + timedelta(days=3, hours=1),
                       capacity=30, tags=["mindfulness"])
    recommend.set_interests(db, S1, ["Exams"])
    recommend.engage(db, S1, f"r:{diary.id}", "saved")
    recommend.set_interests(db, S2, ["exams"])
    recommend.engage(db, S2, f"e:{w2.id}", "attended")
    recommend.set_interests(db, S3, ["sleep"])
    recommend.engage(db, S3, f"r:{r1.id}", "saved")
    db.ids = {"R1": f"r:{r1.id}", "R2": f"r:{r2.id}", "D": f"r:{diary.id}", "W1": f"e:{w1.id}", "W2": f"e:{w2.id}"}
    db.w1, db.w2 = w1, w2
    return db


def _names(db, out):
    back = {v: k for k, v in db.ids.items()}
    return [(back[i["item"]], i["score"]) for i in out["items"]]


def test_worked_example(world):
    out = recommend.recommend(world, S1, 5)
    assert out["cold_start"] is False
    # W1/R2 tie at 1.0 and goes to the event (happening sooner); W2's 3-hop has support 1, so it scores 0
    assert _names(world, out) == [("W1", 1.0), ("R2", 1.0), ("R1", 0.5)]
    assert out["items"][0]["reason"] == "Matches your interest: Exams"
    assert out["items"][2]["reason"] == "Matches your interest: Sleep"
    assert _names(world, recommend.recommend(world, S1, 2)) == [("W1", 1.0), ("R2", 1.0)]  # size-k heap


def test_three_similar_students_unlock_the_three_hop_term(world):
    for s in (S4, S5):
        recommend.set_interests(world, s, ["exams"])
        recommend.engage(world, s, world.ids["W2"], "attended")
    out = recommend.recommend(world, S1, 5)
    # support 3 (S2, S4, S5), each sim 1.0: 0.5 * 3 = 1.5, with a reason that names no one
    assert _names(world, out)[0] == ("W2", 1.5)
    assert out["items"][0]["reason"] == "Popular with students who share your interests"


def test_engaged_past_registered_and_deleted_items_drop_out(world):
    recommend.engage(world, S1, world.ids["R2"], "finished")
    assert "R2" not in dict(_names(world, recommend.recommend(world, S1, 5)))

    events.register(world, world.w1.id, S1)
    clock.advance(timedelta(minutes=10))  # past the cache window
    assert "W1" not in dict(_names(world, recommend.recommend(world, S1, 5)))

    events.remove(world, world.w1.id)
    with pytest.raises(recommend.ItemNotFound):
        recommend.engage(world, S1, world.ids["W1"], "saved")

    world.w2 = events.update(world, world.w2.id, tags=["Exams"])  # tag edits reach the graph at once
    assert _names(world, recommend.recommend(world, S1, 5))[0] == ("W2", 1.0)
    clock.advance(timedelta(days=4))  # W2 has started
    assert "W2" not in dict(_names(world, recommend.recommend(world, S1, 5)))


def test_student_tag_weights_follow_picks_and_engagements(world):
    g = recommend._graph
    assert g.weight(f"s:{S1}", "t:sleep") == 0.5            # one engaged sleep item
    recommend.engage(world, S1, world.ids["R1"], "saved")
    assert g.weight(f"s:{S1}", "t:sleep") == 1.0            # +0.5 per item, capped at 1.0
    recommend.set_interests(world, S1, ["sleep"])
    assert g.weight(f"s:{S1}", "t:sleep") == 1.0
    assert not g.has_edge(f"s:{S1}", "t:exams")             # un-picked, and no engaged exams item
    assert recommend.interests(world, S1) == ["sleep"]


def test_cold_start(world):
    out = recommend.recommend(world, NEW, 3)
    assert out["cold_start"] is True and len(out["items"]) == 3
    assert all(i["score"] == 0.0 for i in out["items"])
    # the items engaged this month (one each): the event first, then the older resource
    assert [n for n, _ in _names(world, out)] == ["W2", "R1", "D"]


def test_rebuild_answers_the_same(world):
    for s in (S4, S5):
        recommend.set_interests(world, s, ["exams"])
        recommend.engage(world, s, world.ids["W2"], "attended")
    before = [recommend.recommend(world, s, 5) for s in (S1, S2, S3, NEW)]
    recommend.rebuild(world)
    assert [recommend.recommend(world, s, 5) for s in (S1, S2, S3, NEW)] == before


def test_validation(world):
    with pytest.raises(ValueError):
        recommend.set_interests(world, S1, ["no-such-tag"])
    with pytest.raises(ValueError):
        recommend.engage(world, S1, world.ids["R1"], "liked")
    with pytest.raises(recommend.ItemNotFound):
        recommend.engage(world, S1, "r:999", "saved")
    assert recommend.engage(world, S1, world.ids["R1"], "saved") is True
    assert recommend.engage(world, S1, world.ids["R1"], "saved") is False
    with pytest.raises(ValueError):
        recommend.create_resource(world, "x", "podcast", "https://x", [])
    with pytest.raises(ValueError):
        recommend.create_resource(world, "x", "audio", "javascript:alert(1)", [])
    with pytest.raises(ValueError):
        recommend.recommend(world, S1, 0)
    assert recommend.tags(world) == ["exams", "mindfulness", "sleep"]
    assert [r.title for r in recommend.resources("SLEEP")] == ["Sleep diary", "Sleep-hygiene guide"]
