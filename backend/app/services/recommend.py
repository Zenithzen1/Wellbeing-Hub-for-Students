"""Recommendations: student-tag-item graph, 2- and 3-hop scoring, top-k heap. Owner: Rithwik.

Plan section 8.
* Graph (our Graph class) with node ids "s:<pseudonym>", "t:<tag>", "r:<resource id>", "e:<event id>":
    student - tag   1.0 if picked; otherwise +0.5 per engaged item with that tag, capped at 1.0
    item - tag      1.0 (item_tags rows, shared with the events service)
    student - item  1.0 when the student attended, saved or finished it
* score(i) = sum_t w(s,t) w(t,i)  +  LAMBDA * sum_{s'} sim(s,s') [s' engaged i],
  sim(s,s') = sum_t w(s,t) w(s',t). The 3-hop term only counts when at least MIN_SUPPORT different
  similar students engaged with i, so a recommendation can never reveal what one person did.
* The best k are kept in a size-k IndexedMinHeap (weakest kept item on top). Ties go to the event
  happening sooner, then to resources.
* Cold start (no tags yet): the k most-engaged items of the last 30 days, then upcoming events.
* Results are cached per student and dropped whenever the graph changes.

Write-through: DB commit first, then the graph. Errors: ValueError (-> 400), ItemNotFound (-> 404).
"""

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import clock
from app.ds import Graph, HashMap, IndexedMinHeap
from app.models import Engagement, Event, Interest, ItemTag, Resource, Tag
from app.services import events

LAMBDA = 0.5
MIN_SUPPORT = 3            # similar students needed before the 3-hop term counts
PICKED = 1.0
PER_ENGAGEMENT = 0.5
COLD_WINDOW = timedelta(days=30)
CACHE_FOR = timedelta(minutes=5)
RESOURCE_KINDS = ("article", "audio", "video")
ENGAGEMENT_KINDS = ("attended", "saved", "finished")
MAX_K = 50


class ItemNotFound(KeyError):
    pass


@dataclass
class ResourceRecord:
    id: int
    title: str
    kind: str
    url: str
    tags: tuple[str, ...]
    created_at: datetime


_lock = threading.RLock()
_graph = Graph()
_resources = HashMap()  # resource id -> ResourceRecord
_picked = HashMap()     # pseudonym -> HashMap(tag name -> True)
_cache = HashMap()      # (pseudonym, k) -> (computed_at, result)


def _s(pse: str) -> str:
    return f"s:{pse}"


def _t(name: str) -> str:
    return f"t:{name}"


def _norm(name: str) -> str:
    return name.strip().lower()


# --- graph upkeep (call with _lock held) --------------------------------------------------------------

def _ensure(g: Graph, node: str, kind: str) -> None:
    if node not in g:
        g.add_node(node, kind)


def _neighbours_of_kind(g: Graph, node: str, kind: str) -> list[tuple[str, float]]:
    return [(x, w) for x, w in g.neighbours(node) if g.kind(x) == kind]


def _refresh_student(g: Graph, picked: HashMap, pse: str) -> None:
    """Recompute the student's tag edges from their picks and engagements."""
    s = _s(pse)
    if s not in g:
        return
    want = HashMap()  # tag node -> weight
    for name in (picked.get(pse) or HashMap()).keys():
        want.put(_t(name), PICKED)
    for item, _ in _neighbours_of_kind(g, s, "item"):
        for t, _ in _neighbours_of_kind(g, item, "tag"):
            if want.get(t, 0.0) < PICKED:
                want.put(t, min(PICKED, want.get(t, 0.0) + PER_ENGAGEMENT))
    for t, _ in _neighbours_of_kind(g, s, "tag"):
        if not want.contains(t):
            g.remove_edge(s, t)
    for t, w in want.items():
        g.add_edge(s, t, w)


def _changed() -> None:
    _cache.clear()


# --- startup ----------------------------------------------------------------------------------------

def rebuild(db: Session) -> None:
    """Rebuild the graph from tags, resources, events, item_tags, interests and engagements."""
    global _graph, _resources, _picked, _cache
    g, resources, picked = Graph(), HashMap(), HashMap()
    for name in db.scalars(select(Tag.name)):
        g.add_node(_t(name), "tag")
    for r in db.scalars(select(Resource)):
        resources.put(r.id, ResourceRecord(r.id, r.title, r.kind, r.url, (), r.created_at))
        g.add_node(f"r:{r.id}", "item")
    for eid in db.scalars(select(Event.id)):
        g.add_node(f"e:{eid}", "item")
    for item, name in db.execute(select(ItemTag.item, Tag.name).join(Tag, Tag.id == ItemTag.tag_id).order_by(Tag.name)):
        if item in g:
            g.add_edge(item, _t(name), 1.0)
            if item.startswith("r:"):
                rec = resources.get(int(item[2:]))
                rec.tags = rec.tags + (name,)
    for pse, name in db.execute(select(Interest.pseudonym, Tag.name).join(Tag, Tag.id == Interest.tag_id)):
        _ensure(g, _s(pse), "student")
        if not picked.contains(pse):
            picked.put(pse, HashMap())
        picked.get(pse).put(name, True)
    for pse, item in db.execute(select(Engagement.pseudonym, Engagement.item)):
        if item in g:
            _ensure(g, _s(pse), "student")
            g.add_edge(_s(pse), item, 1.0)
    for node, _ in g.adj.items():
        if g.kind(node) == "student":
            _refresh_student(g, picked, node[2:])
    with _lock:
        _graph, _resources, _picked, _cache = g, resources, picked, HashMap()


def _on_event_change(event_id: int, tags: tuple[str, ...] | None) -> None:
    """Keep the workshop node in step with the events service (create / edit / delete)."""
    node = f"e:{event_id}"
    with _lock:
        g = _graph
        if node not in g:
            if tags is None:
                return
            g.add_node(node, "item")
        students = [x for x, _ in _neighbours_of_kind(g, node, "student")]
        for x, _ in g.neighbours(node):
            if tags is None or g.kind(x) == "tag":
                g.remove_edge(node, x)
        for name in tags or ():
            _ensure(g, _t(name), "tag")
            g.add_edge(node, _t(name), 1.0)
        for x in students:
            _refresh_student(g, _picked, x[2:])
        _changed()


events.on_change(_on_event_change)


# --- tags, interests, resources ----------------------------------------------------------------------

def tags(db: Session) -> list[str]:
    return list(db.scalars(select(Tag.name).order_by(Tag.name)))


def _tag_rows(db: Session, names: list[str], create: bool) -> list[Tag]:
    clean = sorted({_norm(n) for n in names if n.strip()})
    if any(len(n) > 50 for n in clean):
        raise ValueError("tag names are at most 50 characters")
    rows = []
    for name in clean:
        row = db.scalar(select(Tag).where(Tag.name == name))
        if row is None:
            if not create:
                raise ValueError(f"unknown tag: {name}")
            row = Tag(name=name)
            db.add(row)
            db.flush()
        rows.append(row)
    return rows


def interests(db: Session, pseudonym: str) -> list[str]:
    return list(db.scalars(select(Tag.name).join(Interest, Interest.tag_id == Tag.id)
                           .where(Interest.pseudonym == pseudonym).order_by(Tag.name)))


def set_interests(db: Session, pseudonym: str, names: list[str]) -> list[str]:
    """Replace the student's picked tags (only tags the department curates)."""
    rows = _tag_rows(db, names, create=False)
    db.execute(delete(Interest).where(Interest.pseudonym == pseudonym))
    now = clock.now()
    for row in rows:
        db.add(Interest(pseudonym=pseudonym, tag_id=row.id, weight=PICKED, at=now))
    db.commit()
    picked = [row.name for row in rows]
    with _lock:
        mine = HashMap()
        for name in picked:
            mine.put(name, True)
        _picked.put(pseudonym, mine)
        _ensure(_graph, _s(pseudonym), "student")
        _refresh_student(_graph, _picked, pseudonym)
        _changed()
    return picked


def resources(tag: str | None = None) -> list[ResourceRecord]:
    """All resources, newest first, optionally with one tag."""
    with _lock:
        recs = _resources.values()
    if tag:
        recs = [r for r in recs if _norm(tag) in r.tags]
    return sorted(recs, key=lambda r: (r.created_at, r.id), reverse=True)


def create_resource(db: Session, title: str, kind: str, url: str, tag_names: list[str]) -> ResourceRecord:
    """Admin adds an item; unknown tag names are added to the curated list (as events do)."""
    title, url = title.strip(), url.strip()
    if not title:
        raise ValueError("title is required")
    if kind not in RESOURCE_KINDS:
        raise ValueError(f"kind must be one of {', '.join(RESOURCE_KINDS)}")
    if not (url.startswith("https://") or url.startswith("http://") or url.startswith("/")):
        raise ValueError("url must start with https://, http:// or /")
    row = Resource(title=title, kind=kind, url=url, created_at=clock.now())
    db.add(row)
    db.flush()
    tag_rows = _tag_rows(db, tag_names, create=True)
    for t in tag_rows:
        db.add(ItemTag(item=f"r:{row.id}", tag_id=t.id))
    db.commit()
    rec = ResourceRecord(row.id, row.title, row.kind, row.url, tuple(t.name for t in tag_rows), row.created_at)
    with _lock:
        _resources.put(rec.id, rec)
        _graph.add_node(f"r:{rec.id}", "item")
        for name in rec.tags:
            _ensure(_graph, _t(name), "tag")
            _graph.add_edge(f"r:{rec.id}", _t(name), 1.0)
        _changed()
    return rec


def my_engagements(db: Session, pseudonym: str) -> HashMap:
    """item -> list of kinds, for the caller's own badges ("saved", "finished")."""
    out = HashMap()
    for item, kind in db.execute(select(Engagement.item, Engagement.kind).where(Engagement.pseudonym == pseudonym)):
        if not out.contains(item):
            out.put(item, [])
        out.get(item).append(kind)
    return out


def _item_exists(item: str) -> bool:
    kind, _, raw = item.partition(":")
    if not raw.isdigit():
        return False
    if kind == "r":
        with _lock:
            return _resources.contains(int(raw))
    if kind == "e":
        try:
            events.get(int(raw))
            return True
        except events.EventNotFound:
            return False
    return False


def engage(db: Session, pseudonym: str, item: str, kind: str) -> bool:
    """Record an engagement. True if new, False if it was already recorded."""
    if kind not in ENGAGEMENT_KINDS:
        raise ValueError(f"kind must be one of {', '.join(ENGAGEMENT_KINDS)}")
    if not _item_exists(item):
        raise ItemNotFound(item)
    exists = db.scalar(select(Engagement.id).where(Engagement.pseudonym == pseudonym, Engagement.item == item,
                                                   Engagement.kind == kind))
    if exists is not None:
        return False
    db.add(Engagement(pseudonym=pseudonym, item=item, kind=kind, at=clock.now()))
    db.commit()
    with _lock:
        g = _graph
        _ensure(g, _s(pseudonym), "student")
        _ensure(g, item, "item")
        g.add_edge(_s(pseudonym), item, 1.0)
        _refresh_student(g, _picked, pseudonym)
        _changed()
    return True


# --- scoring --------------------------------------------------------------------------------------------

def _walk(pse: str) -> tuple[HashMap, HashMap, HashMap, HashMap, HashMap] | None:
    """2- and 3-hop walk from the student (call with _lock held). None = cold start (no tags)."""
    g, s = _graph, _s(pse)
    if s not in g:
        return None
    my_tags = _neighbours_of_kind(g, s, "tag")
    if not my_tags:
        return None
    two, why, sim = HashMap(), HashMap(), HashMap()
    for t, wst in my_tags:                         # hop 1: my tags
        for x, w in g.neighbours(t):               # hop 2: their items and the other students on them
            kind = g.kind(x)
            if kind == "item":
                two.put(x, two.get(x, 0.0) + wst * w)
                if not why.contains(x):
                    why.put(x, HashMap())
                why.get(x).put(t[2:], wst * w)
            elif kind == "student" and x != s:
                sim.put(x, sim.get(x, 0.0) + wst * w)
    three, support = HashMap(), HashMap()
    for other, sm in sim.items():                  # hop 3: what similar students engaged with
        for x, _ in _neighbours_of_kind(g, other, "item"):
            three.put(x, three.get(x, 0.0) + sm)
            support.put(x, support.get(x, 0) + 1)
    mine = HashMap()
    for x, _ in _neighbours_of_kind(g, s, "item"):
        mine.put(x, True)
    return two, why, three, support, mine


def _describe(item: str) -> dict | None:
    """Item details, or None if it is gone or is an event that has already started."""
    kind, _, raw = item.partition(":")
    if kind == "r":
        with _lock:
            rec = _resources.get(int(raw))
        if rec is None:
            return None
        return {"item": item, "type": "resource", "id": rec.id, "title": rec.title, "tags": list(rec.tags),
                "resource_kind": rec.kind, "url": rec.url, "start": None, "end": None, "location": None}
    try:
        ev = events.get(int(raw))
    except events.EventNotFound:
        return None
    if ev.start <= clock.now():
        return None
    return {"item": item, "type": "event", "id": ev.id, "title": ev.title, "tags": list(ev.tags),
            "resource_kind": None, "url": None, "start": ev.start, "end": ev.end, "location": ev.location}


def _rank(score: float, info: dict) -> tuple:
    """Bigger is better: score, then events before resources, then the sooner event / older resource."""
    if info["type"] == "event":
        return (score, 1, -info["start"].timestamp())
    return (score, 0, -info["id"])


def _top_k(scored: list[tuple[float, dict]], k: int) -> list[dict]:
    """Size-k min-heap: the weakest kept item is on top and is replaced by anything better. O(m log k)"""
    heap, infos = IndexedMinHeap(), HashMap()
    for score, info in scored:
        heap.push(info["item"], _rank(score, info))
        infos.put(info["item"], (score, info))
        if len(heap) > k:
            heap.pop()
    out = []
    while len(heap):
        item, _ = heap.pop()
        score, info = infos.get(item)
        out.append({**info, "score": round(score, 4)})
    out.reverse()
    return out


def _skip_registered(db: Session, pse: str, infos: list[dict]) -> list[dict]:
    ids = [i["id"] for i in infos if i["type"] == "event"]
    if not ids:
        return infos
    status = events.statuses_for(db, pse, ids)
    return [i for i in infos if i["type"] != "event" or status.get(i["id"]) is None]


def _personal(db: Session, pse: str, k: int, walk) -> list[dict]:
    two, why, three, support, mine = walk
    candidates = HashMap()
    for x, _ in two.items():
        candidates.put(x, True)
    for x, _ in three.items():
        candidates.put(x, True)
    scored = []
    for x in candidates.keys():
        if mine.contains(x):
            continue
        score = two.get(x, 0.0)
        if support.get(x, 0) >= MIN_SUPPORT:
            score += LAMBDA * three.get(x, 0.0)
        score = round(score, 9)
        if score <= 0:
            continue
        info = _describe(x)
        if info is None:
            continue
        contrib = why.get(x)
        if contrib is not None:
            best = sorted(contrib.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
            info["reason"] = "Matches your interest: " + ", ".join(name.title() for name, _ in best)
        else:
            info["reason"] = "Popular with students who share your interests"
        scored.append((score, info))
    return _top_k(_scored_unregistered(db, pse, scored), k)


def _cold(db: Session, pse: str, k: int) -> list[dict]:
    """The k most-engaged items of the last 30 days, then upcoming events, then newest resources."""
    counts = HashMap()
    since = clock.now() - COLD_WINDOW
    for item, who in db.execute(select(Engagement.item, Engagement.pseudonym).where(Engagement.at >= since)):
        if who != pse:
            counts.put(item, counts.get(item, 0) + 1)
    mine = my_engagements(db, pse)
    scored = []
    for item, n in counts.items():
        info = None if mine.contains(item) else _describe(item)
        if info is not None:
            info["reason"] = "Popular with students this month"
            scored.append((float(n), info))
    out = _top_k(_scored_unregistered(db, pse, scored), k)
    if len(out) < k:
        seen = HashMap()
        for info in out:
            seen.put(info["item"], True)
        extra = []
        for item in [f"e:{ev.id}" for ev in events.upcoming(k + 20)] + [f"r:{r.id}" for r in resources()]:
            info = None if seen.contains(item) or mine.contains(item) else _describe(item)
            if info is not None:
                info["reason"] = "Coming up soon" if info["type"] == "event" else "New in the library"
                extra.append(info)
        out += _skip_registered(db, pse, extra)[: k - len(out)]
    for info in out:
        info["score"] = 0.0  # cold start is ordered by popularity; there is no personal score
    return out


def _scored_unregistered(db: Session, pse: str, scored: list[tuple[float, dict]]) -> list[tuple[float, dict]]:
    ok = HashMap()
    for info in _skip_registered(db, pse, [info for _, info in scored]):
        ok.put(info["item"], True)
    return [(s, i) for s, i in scored if ok.contains(i["item"])]


def recommend(db: Session, pseudonym: str, k: int = 5) -> dict:
    """{"cold_start": bool, "items": [...]} for this student, best first."""
    if not 1 <= k <= MAX_K:
        raise ValueError(f"k must be 1 to {MAX_K}")
    now = clock.now()
    with _lock:
        hit = _cache.get((pseudonym, k))
        if hit is not None and now - hit[0] < CACHE_FOR:
            return hit[1]
        walk = _walk(pseudonym)
    if walk is None:
        result = {"cold_start": True, "items": _cold(db, pseudonym, k)}
    else:
        result = {"cold_start": False, "items": _personal(db, pseudonym, k, walk)}
    with _lock:
        _cache.put((pseudonym, k), (now, result))
    return result


def resource_dict(rec: ResourceRecord, mine: list[str] | None = None) -> dict:
    return {"id": rec.id, "item": f"r:{rec.id}", "title": rec.title, "kind": rec.kind, "url": rec.url,
            "tags": list(rec.tags), "created_at": rec.created_at, "my": mine or []}
