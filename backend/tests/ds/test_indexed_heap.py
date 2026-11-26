"""IndexedMinHeap: randomised against a plain dict, plus the plan's waitlist example (section 5)."""

import random

import pytest

from app.ds import IndexedMinHeap


def check(heap):
    """Heap order holds and the position map points at every entry."""
    for i in range(len(heap)):
        for child in (2 * i + 1, 2 * i + 2):
            if child < len(heap):
                assert not heap.arr[child][1] < heap.arr[i][1]
        assert heap.pos.get(heap.arr[i][0]) == i
    assert len(heap.pos) == len(heap)


def test_matches_brute_force():
    rng = random.Random(7)
    heap, naive = IndexedMinHeap(), {}
    next_id = 0
    for step in range(5000):
        op = rng.random()
        if op < 0.4 or not naive:
            heap.push(next_id, (rng.randrange(3), rng.randrange(1000), next_id))
            naive[next_id] = heap.arr[heap.pos.get(next_id)][1]
            next_id += 1
        elif op < 0.6:
            eid, key = heap.pop()
            assert key == min(naive.values())
            assert naive.pop(eid) == key
        elif op < 0.8:
            eid = rng.choice(list(naive))
            assert heap.remove(eid) == naive.pop(eid)
        else:
            eid = rng.choice(list(naive))
            key = (rng.randrange(3), rng.randrange(1000), eid)
            heap.update(eid, key)
            naive[eid] = key
        assert len(heap) == len(naive)
        if naive:
            assert heap.peek()[1] == min(naive.values())
        if step % 100 == 0:
            check(heap)
    check(heap)


def test_build_heap_then_drain_in_order():
    rng = random.Random(3)
    pairs = [(i, (rng.randrange(2), rng.randrange(500), i)) for i in range(300)]
    heap = IndexedMinHeap()
    heap.build_heap(pairs)
    check(heap)
    out = [heap.pop()[1] for _ in range(len(pairs))]
    assert out == sorted(key for _, key in pairs)
    with pytest.raises(ValueError):
        heap.build_heap([(1, 1), (1, 2)])


def test_plan_waitlist_example():
    """C, A normal; B urgent; D normal; E urgent. D leaves, B is offered, C ages to urgent and goes first."""
    heap = IndexedMinHeap()
    joined = {"C": 1, "A": 2, "B": 3, "D": 4, "E": 5}
    tier = {"C": 1, "A": 1, "B": 0, "D": 1, "E": 0}
    for name in "CABDE":
        heap.push(name, (tier[name], joined[name]))
    assert heap.peek()[0] == "B"
    heap.remove("D")
    assert heap.pop()[0] == "B"
    heap.update("C", (0, joined["C"]))  # ageing keeps the join time
    assert [heap.pop()[0] for _ in range(3)] == ["C", "E", "A"]


def test_errors():
    heap = IndexedMinHeap()
    with pytest.raises(IndexError):
        heap.pop()
    heap.push("x", 1)
    with pytest.raises(ValueError):
        heap.push("x", 2)
    with pytest.raises(KeyError):
        heap.remove("y")
    with pytest.raises(KeyError):
        heap.update("y", 0)
