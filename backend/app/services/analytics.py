"""Analytics: hash-map aggregates with k-suppression (no count 1-4 ever leaves). Owner: Rithwik.

Plan section 9. Reads only operational tables (pseudonyms, categories, times) and only ever returns
counts, rates and a median, computed on demand in one pass per table with our HashMap.

* Buckets are whole ISO weeks in Dubai time: the range is widened to Monday .. Sunday.
* k-anonymity: any count 1..4 is shown as "<5" (0 is shown; it points at nobody).
* Complementary suppression: in any line whose total can be seen or worked out (a column with a
  "total" row, the whole table when its grand total is known) and that has exactly one hidden cell,
  the next-smallest visible cell is hidden too ("hidden"), so the total can't give the small cell away.
* Rates are hidden when their numerator is 1..4 or their denominator is under 5; a median needs
  at least 5 values. No per-counsellor figures below 5 sessions. The CSV is the same data.
"""

import csv
import io
import statistics
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.ds import HashMap
from app.models import Availability, Booking, Event, ItemTag, Notification, Offer, Registration, Tag, WaitlistEntry
from app.services import booking

K = 5
SMALL = "<5"
HIDDEN = "hidden"
DEFAULT_WEEKS = 8
MAX_WEEKS = 53
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEFAULT_HOURS = (9, 17)


# --- k-anonymity --------------------------------------------------------------------------------

def shown(n: int) -> int | str:
    """A single count as it may leave the server."""
    return SMALL if 0 < n < K else n


def suppress(cells: list[list[int]], rows: bool = False, cols: bool = False,
             whole: bool = False) -> list[list[int | str]]:
    """Counts 1..4 -> "<5"; then complementary suppression, repeated until stable, over the lines
    whose sums are known: every row (rows=True), every column (cols=True), the whole table (whole=True)."""
    n = len(cells)
    m = len(cells[0]) if n else 0
    small = [[0 < c < K for c in row] for row in cells]
    comp = [[False] * m for _ in range(n)]
    lines = []
    if rows:
        lines += [[(i, j) for j in range(m)] for i in range(n)]
    if cols:
        lines += [[(i, j) for i in range(n)] for j in range(m)]
    if whole:
        lines.append([(i, j) for i in range(n) for j in range(m)])
    changed = True
    while changed:
        changed = False
        for line in lines:
            hidden = [p for p in line if small[p[0]][p[1]] or comp[p[0]][p[1]]]
            if len(hidden) != 1:
                continue
            visible = [p for p in line if not (small[p[0]][p[1]] or comp[p[0]][p[1]])]
            if not visible:
                continue
            # the next-smallest cell; a non-zero one where possible (hiding a 0 protects little)
            i, j = min(visible, key=lambda p: (cells[p[0]][p[1]] == 0, cells[p[0]][p[1]], p))
            comp[i][j] = True
            changed = True
    return [[SMALL if small[i][j] else HIDDEN if comp[i][j] else cells[i][j] for j in range(m)] for i in range(n)]


def _table(rows: list[str], cols: list[str], counts: HashMap, totals: bool = False, whole: bool = False) -> dict:
    """totals=True adds a total per column and a grand total, so those lines get complementary
    suppression. whole=True protects a table whose grand total is shown elsewhere."""
    cells = [[counts.get((r, c), 0) for c in cols] for r in rows]
    out = {"rows": rows, "cols": cols, "cells": suppress(cells, cols=totals, whole=totals or whole),
           "totals": None, "grand_total": None}
    if totals:
        out["totals"] = [shown(sum(cells[i][j] for i in range(len(rows)))) for j in range(len(cols))]
        out["grand_total"] = shown(sum(sum(row) for row in cells))
    return out


def _rate(num: int, den: int) -> float | str | None:
    if den == 0:
        return None
    if den < K or 0 < num < K:
        return SMALL
    return round(num / den, 3)


# --- time buckets -------------------------------------------------------------------------------------

def _week(dt: datetime) -> str:
    iso = clock.to_local(dt).date().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _range(first: date | None, last: date | None) -> tuple[date, date]:
    """Whole weeks: first is moved back to its Monday, last forward to its Sunday."""
    last = last or clock.to_local(clock.now()).date()
    first = first or last - timedelta(weeks=DEFAULT_WEEKS - 1)
    if last < first:
        raise ValueError("'to' must not be before 'from'")
    first -= timedelta(days=first.weekday())
    last += timedelta(days=6 - last.weekday())
    if (last - first).days + 1 > MAX_WEEKS * 7:
        raise ValueError(f"at most {MAX_WEEKS} weeks at a time")
    return first, last


def _utc_bounds(first: date, last: date) -> tuple[datetime, datetime]:
    return (datetime.combine(first, time(0), tzinfo=clock.DUBAI),
            datetime.combine(last + timedelta(days=1), time(0), tzinfo=clock.DUBAI))


def _bump(counts: HashMap, key, by: int = 1) -> None:
    counts.put(key, counts.get(key, 0) + by)


# --- the dashboard ----------------------------------------------------------------------------------------

def summary(db: Session, first: date | None = None, last: date | None = None) -> dict:
    first, last = _range(first, last)
    lo, hi = _utc_bounds(first, last)
    weeks = [_week(datetime.combine(first + timedelta(weeks=i), time(12), tzinfo=clock.DUBAI))
             for i in range(((last - first).days + 1) // 7)]

    # bookings: one pass into hash maps keyed (reason, week), (weekday, hour), week, counsellor
    by_reason, peak, outcome = HashMap(), HashMap(), HashMap()
    sessions, booked_min = HashMap(), HashMap()
    for b in db.scalars(select(Booking).where(Booking.start >= lo, Booking.start < hi)):
        wk = _week(b.start)
        _bump(outcome, (wk, "all"))
        _bump(outcome, (wk, b.status))
        if b.status == "cancelled":
            continue
        _bump(by_reason, (b.reason, wk))
        local = clock.to_local(b.start)
        _bump(peak, (WEEKDAYS[local.weekday()], local.hour))
        _bump(sessions, b.counsellor_id)
        _bump(booked_min, b.counsellor_id, int((b.end - b.start).total_seconds() // 60))

    reasons = list(booking.REASONS)
    hours_seen = [h for (_, h), _ in peak.items()]
    h0, h1 = (min(hours_seen), max(hours_seen)) if hours_seen else DEFAULT_HOURS
    hour_cols = list(range(h0, h1 + 1))
    peak_counts = HashMap()
    for (day, h), n in peak.items():
        peak_counts.put((day, f"{h:02d}:00"), n)

    return {
        "first_day": first, "last_day": last, "k": K, "weeks": weeks,
        "bookings_by_reason": _table(reasons, weeks, by_reason, totals=True),
        "outcomes": [{"week": wk,
                      "cancel_rate": _rate(outcome.get((wk, "cancelled"), 0), outcome.get((wk, "all"), 0)),
                      "no_show_rate": _rate(outcome.get((wk, "no_show"), 0),
                                            outcome.get((wk, "no_show"), 0) + outcome.get((wk, "completed"), 0))}
                     for wk in weeks],
        "utilisation": _utilisation(db, lo, hi, sessions, booked_min),
        "waitlist_now": _waitlist_now(db),
        "waitlist_weeks": _waitlist_weeks(db, lo, hi, weeks),
        "events_by_tag": _events_by_tag(db, lo, hi),
        # its grand total equals bookings_by_reason's, so the whole table is protected
        "peak_demand": _table(list(WEEKDAYS), [f"{h:02d}:00" for h in hour_cols], peak_counts, whole=True),
    }


def _utilisation(db: Session, lo: datetime, hi: datetime, sessions: HashMap, booked_min: HashMap) -> list[dict]:
    """Booked minutes / available minutes per counsellor; nothing shown below 5 sessions."""
    avail = HashMap()
    for a in db.scalars(select(Availability).where(Availability.start < hi, Availability.end > lo)):
        minutes = int((min(a.end, hi) - max(a.start, lo)).total_seconds() // 60)
        _bump(avail, a.counsellor_id, minutes if a.kind == "open" else -minutes)
    out = []
    for rec in booking.counsellors():
        n, free = sessions.get(rec.id, 0), max(0, avail.get(rec.id, 0))
        ok = n >= K
        out.append({"counsellor_id": rec.id, "counsellor": rec.display_name, "sessions": n if ok else SMALL,
                    "available_hours": round(free / 60, 1),
                    "utilisation": round(min(1.0, booked_min.get(rec.id, 0) / free), 3) if ok and free else None})
    return out


def _waitlist_now(db: Session) -> dict:
    """Current line sizes (the heaps), urgent vs normal."""
    counts = HashMap()
    for (tier,) in db.execute(select(WaitlistEntry.tier).where(WaitlistEntry.status.in_(("waiting", "offered")))):
        _bump(counts, ("waiting now", "urgent" if tier == 0 else "normal"))
    return _table(["waiting now"], ["urgent", "normal"], counts, totals=True)


def _waitlist_weeks(db: Session, lo: datetime, hi: datetime, weeks: list[str]) -> list[dict]:
    """Joins per week, and the median wait from joining to the first offer (offers made that week)."""
    joined = HashMap()
    for (at,) in db.execute(select(WaitlistEntry.joined_at).where(WaitlistEntry.joined_at >= lo,
                                                                  WaitlistEntry.joined_at < hi)):
        _bump(joined, _week(at))
    offered_at = HashMap()  # offer id -> when it was made (its "waitlist_offer" notification)
    for ref, at in db.execute(select(Notification.ref, Notification.send_at).where(
            Notification.kind == "waitlist_offer", Notification.ref.like("offer:%"))):
        if ref[6:].isdigit():
            offered_at.put(int(ref[6:]), at)
    first_offer = HashMap()  # waitlist entry id -> (first offer time, joined_at)
    for oid, wid, joined_at in db.execute(select(Offer.id, Offer.waitlist_id, WaitlistEntry.joined_at)
                                          .join(WaitlistEntry, WaitlistEntry.id == Offer.waitlist_id)):
        at = offered_at.get(oid)
        if at is not None and (not first_offer.contains(wid) or at < first_offer.get(wid)[0]):
            first_offer.put(wid, (at, joined_at))
    waits = HashMap()  # week -> list of hours
    for _, (at, joined_at) in first_offer.items():
        if lo <= at < hi:
            wk = _week(at)
            if not waits.contains(wk):
                waits.put(wk, [])
            waits.get(wk).append((at - joined_at).total_seconds() / 3600)
    out = []
    for wk in weeks:
        w = waits.get(wk, [])
        out.append({"week": wk, "joined": shown(joined.get(wk, 0)), "offers": shown(len(w)),
                    "median_wait_hours": round(statistics.median(w), 1) if len(w) >= K else None})
    return out


def _events_by_tag(db: Session, lo: datetime, hi: datetime) -> dict:
    """Registrations x event tags, for events starting in the range."""
    tags_of = HashMap()  # event id -> list of tag names
    for item, name in db.execute(select(ItemTag.item, Tag.name).join(Tag, Tag.id == ItemTag.tag_id)
                                 .where(ItemTag.item.like("e:%"))):
        eid = int(item[2:])
        if not tags_of.contains(eid):
            tags_of.put(eid, [])
        tags_of.get(eid).append(name)
    counts, names = HashMap(), HashMap()
    for (eid,) in db.execute(select(Registration.event_id).join(Event, Event.id == Registration.event_id)
                             .where(Registration.status == "registered", Event.start >= lo, Event.start < hi)):
        for name in tags_of.get(eid, []):
            _bump(counts, ("registrations", name))
            names.put(name, True)
    return _table(["registrations"], sorted(names.keys()), counts)


# --- CSV export: exactly what the dashboard shows -------------------------------------------------------

def to_csv(data: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["metric", "row", "column", "value"])
    for metric in ("bookings_by_reason", "peak_demand", "events_by_tag", "waitlist_now"):
        t = data[metric]
        for r, row in zip(t["rows"], t["cells"]):
            for c, v in zip(t["cols"], row):
                w.writerow([metric, r, c, v])
        if t["totals"] is not None:
            for c, v in zip(t["cols"], t["totals"]):
                w.writerow([metric, "total", c, v])
            w.writerow([metric, "total", "all", t["grand_total"]])
    for row in data["outcomes"]:
        for key in ("cancel_rate", "no_show_rate"):
            w.writerow(["outcomes", row["week"], key, "" if row[key] is None else row[key]])
    for row in data["waitlist_weeks"]:
        for key in ("joined", "offers", "median_wait_hours"):
            w.writerow(["waitlist_weeks", row["week"], key, "" if row[key] is None else row[key]])
    for row in data["utilisation"]:
        for key in ("sessions", "available_hours", "utilisation"):
            w.writerow(["utilisation", row["counsellor"], key, "" if row[key] is None else row[key]])
    return buf.getvalue()
