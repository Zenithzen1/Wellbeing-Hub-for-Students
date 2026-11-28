"""Analytics: k = 5 suppression, complementary suppression, and that no count 1..4 ever leaves."""

from datetime import date, datetime, timedelta

import pytest

from app import clock
from app.models import Availability, Booking, Event, ItemTag, Notification, Offer, Registration, Tag, WaitlistEntry
from app.services import analytics, booking

W47, W48 = date(2026, 11, 16), date(2026, 11, 23)  # Mondays


def walk_counts(obj, path=""):
    """Every int in the output, except ids and k."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key not in ("k", "counsellor_id"):
                yield from walk_counts(val, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from walk_counts(val, f"{path}[{i}]")
    elif isinstance(obj, int) and not isinstance(obj, bool):
        yield path, obj


def test_suppress_matches_the_plan_example():
    # rows: academic, anxiety, relationships, homesickness, other; columns: weeks 45, 46, 47
    cells = [[12, 18, 23], [9, 7, 11], [6, 3, 4], [2, 1, 2], [5, 6, 8]]
    out = analytics.suppress(cells, cols=True, whole=True)
    # week 45 has one small cell (homesickness 2), so its next-smallest cell (other 5) is hidden too
    assert [row[0] for row in out] == [12, 9, 6, "<5", "hidden"]
    assert [row[1] for row in out] == [18, 7, "<5", "<5", 6]
    assert [row[2] for row in out] == [23, 11, "<5", "<5", 8]
    # with row sums known too, rows get the same treatment until stable
    assert analytics.suppress([[2, 9, 7]], rows=True) == [["<5", 9, "hidden"]]
    assert analytics.suppress([[2, 0, 9]], rows=True) == [["<5", 0, "hidden"]]  # a non-zero partner
    assert analytics.suppress([[0, 5, 7]], rows=True, cols=True, whole=True) == [[0, 5, 7]]


def _at(monday: date, i: int) -> datetime:
    return datetime(monday.year, monday.month, monday.day, 9 + (i // 5) % 8, tzinfo=clock.DUBAI) + timedelta(days=i % 5)


def _book(db, cid, monday, reason, n, statuses=("completed",)):
    for i in range(n):
        start = _at(monday, i)
        db.add(Booking(counsellor_id=cid, pseudonym=f"{i:064x}", start=start, end=start + timedelta(minutes=45),
                       reason=reason, status=statuses[i] if i < len(statuses) else statuses[-1],
                       created_at=start - timedelta(days=2)))


@pytest.fixture
def data(db):
    booking.rebuild(db)
    noor = booking.add_counsellor(db, 100, "Dr Noor").id
    mehta = booking.add_counsellor(db, 101, "Dr Mehta").id
    # week 47: 28 sessions (3 no-shows) + 6 cancelled; sleep has 2
    _book(db, noor, W47, "academic_stress", 12, ("no_show",) * 3 + ("completed",))
    _book(db, noor, W47, "anxiety", 9)
    _book(db, noor, W47, "other", 5)
    _book(db, noor, W47, "sleep", 2)
    _book(db, noor, W47, "academic_stress", 6, ("cancelled",))
    # week 48: academic 7 + Dr Mehta's 3, relationships 6, sleep 3, low mood 1
    _book(db, noor, W48, "academic_stress", 7)
    _book(db, noor, W48, "relationships", 6)
    _book(db, noor, W48, "sleep", 3)
    _book(db, noor, W48, "low_mood", 1)
    _book(db, mehta, W48, "academic_stress", 3)
    for monday in (W47, W48):  # Dr Noor: 5 x 8 h open each week
        for d in range(5):
            s = datetime(monday.year, monday.month, monday.day, 9, tzinfo=clock.DUBAI) + timedelta(days=d)
            db.add(Availability(counsellor_id=noor, start=s, end=s + timedelta(hours=8), kind="open"))
    # waitlist: 2 urgent + 4 normal waiting now; 5 earlier entries got offers 10..50 h after joining
    for tier in (0, 0, 1, 1, 1, 1):
        db.add(WaitlistEntry(counsellor_id=noor, pseudonym="f" * 64, tier=tier, joined_at=_at(W48, 0)))
    for h in (10, 20, 30, 40, 50):
        offered = _at(W48, 3)
        e = WaitlistEntry(counsellor_id=noor, pseudonym="e" * 64, tier=1, joined_at=offered - timedelta(hours=h),
                          status="booked")
        db.add(e)
        db.flush()
        o = Offer(waitlist_id=e.id, counsellor_id=noor, start=offered + timedelta(days=1),
                  end=offered + timedelta(days=1, minutes=45), expires_at=offered + timedelta(minutes=30),
                  status="accepted")
        db.add(o)
        db.flush()
        db.add(Notification(recipient="e" * 64, kind="waitlist_offer", payload="{}", send_at=offered,
                            status="sent", ref=f"offer:{o.id}"))
    # events in week 48: a workshop tagged exams + sleep with 7 registered, a yoga class with 2
    exams, sleep, yoga = Tag(name="exams"), Tag(name="sleep"), Tag(name="yoga")
    db.add_all([exams, sleep, yoga])
    for title, tags, n in (("Exam stress", (exams, sleep), 7), ("Yoga", (yoga,), 2)):
        ev = Event(title=title, start=_at(W48, 4), end=_at(W48, 4) + timedelta(hours=1), capacity=30)
        db.add(ev)
        db.flush()
        for t in tags:
            db.add(ItemTag(item=f"e:{ev.id}", tag_id=t.id))
        for i in range(n):
            db.add(Registration(event_id=ev.id, pseudonym=f"{i:064x}", status="registered", position=0))
    db.commit()
    db.noor, db.mehta = noor, mehta
    return db


def test_summary(data):
    out = analytics.summary(data, date(2026, 11, 18), date(2026, 11, 25))
    assert (out["first_day"], out["last_day"]) == (W47, date(2026, 11, 29))  # whole weeks
    assert out["weeks"] == ["2026-W47", "2026-W48"]

    t = out["bookings_by_reason"]
    cells = dict(zip(t["rows"], t["cells"]))
    assert cells["academic_stress"] == [12, 10] and cells["anxiety"] == [9, 0]
    assert cells["sleep"] == ["<5", "<5"] and cells["low_mood"] == [0, "<5"]
    assert cells["other"] == ["hidden", 0]  # complement for week 47's lone small cell
    assert t["totals"] == [28, 20] and t["grand_total"] == 48

    assert out["outcomes"][0] == {"week": "2026-W47", "cancel_rate": round(6 / 34, 3), "no_show_rate": "<5"}
    assert out["outcomes"][1]["cancel_rate"] == 0.0

    util = {u["counsellor"]: u for u in out["utilisation"]}
    assert util["Dr Noor"]["sessions"] == 45 and util["Dr Noor"]["utilisation"] == round(45 * 45 / 4800, 3)
    assert util["Dr Mehta"]["sessions"] == "<5" and util["Dr Mehta"]["utilisation"] is None

    assert out["waitlist_now"]["cells"] == [["<5", "<5"]] and out["waitlist_now"]["grand_total"] == 6
    w48 = out["waitlist_weeks"][1]
    assert w48["offers"] == 5 and w48["median_wait_hours"] == 30.0
    assert out["waitlist_weeks"][0]["median_wait_hours"] is None

    ev = out["events_by_tag"]
    assert dict(zip(ev["cols"], ev["cells"][0])) == {"exams": 7, "sleep": 7, "yoga": "<5"}


def test_no_count_between_1_and_4_ever_leaves(data):
    for first, last in ((date(2026, 11, 18), date(2026, 11, 25)), (W48, W48), (None, None)):
        out = analytics.summary(data, first, last)
        bad = [(p, n) for p, n in walk_counts(out) if 1 <= n <= 4]
        assert bad == []
        assert "<5" in analytics.to_csv(out) or first is None


def test_csv_is_the_dashboard(data):
    out = analytics.summary(data, W47, W48)
    text = analytics.to_csv(out)
    assert text.splitlines()[0] == "metric,row,column,value"
    assert "bookings_by_reason,other,2026-W47,hidden" in text
    assert "bookings_by_reason,total,all,48" in text
    assert "0" * 64 not in text and "f" * 64 not in text  # no pseudonyms, no row-level data


def test_range_validation(data):
    with pytest.raises(ValueError):
        analytics.summary(data, W48, W47)
    with pytest.raises(ValueError):
        analytics.summary(data, date(2025, 1, 1), date(2026, 6, 1))
