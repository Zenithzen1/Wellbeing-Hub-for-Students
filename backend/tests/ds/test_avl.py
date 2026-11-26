"""AVLTree (plan section 6): randomised against a plain dict + sorted list, check() after every op."""

import math
import random

import pytest

from app.ds import AVLTree


def test_empty_tree():
    t = AVLTree()
    assert len(t) == 0 and t.height() == 0
    t.check()
    assert list(t.range(0, 100)) == []
    assert list(t.next_k(0, 5)) == []
    with pytest.raises(KeyError):
        t.find(1)
    with pytest.raises(KeyError):
        t.delete(1)


def test_rotation_on_date_order_inserts():
    """1, 3, 5 Dec inserted in order: one left rotation makes 3 the root (plan 6.1)."""
    t = AVLTree()
    for day in (1, 3, 5):
        t.insert(day, f"{day} Dec")
        t.check()
    assert t.root.key == 3 and t.height() == 2


def test_sorted_inserts_stay_logarithmic():
    t = AVLTree()
    n = 10000
    for i in range(n):
        t.insert(i, i)
    t.check()
    assert t.height() < 1.44 * math.log2(n + 2)


def test_insert_existing_key_overwrites_value():
    t = AVLTree()
    t.insert(5, "a")
    t.insert(5, "b")
    assert len(t) == 1 and t.find(5) == "b"


def test_range_worked_example():
    """'What's on between 3 and 9 Dec?' over the seven events of plan 6.2."""
    t = AVLTree()
    events = {28: "Yoga at dawn", 1: "Exam-stress workshop", 3: "Sleep clinic", 5: "Art therapy",
              8: "Peer circle", 10: "Mindfulness hour", 12: "Winter wellness fair"}
    for day, title in events.items():
        key = (day + 100 if day < 28 else day, 0)  # Dec days sort after 28 Nov
        t.insert(key, title)
    got = [title for _, title in t.range((103, 0), (109, 0))]
    assert got == ["Sleep clinic", "Art therapy", "Peer circle"]


def test_range_bounds_are_inclusive_and_lo_gt_hi_is_empty():
    t = AVLTree()
    for i in range(10):
        t.insert(i, i)
    assert [k for k, _ in t.range(3, 6)] == [3, 4, 5, 6]
    assert list(t.range(6, 3)) == []


def test_next_k_is_strictly_after():
    t = AVLTree()
    for i in range(0, 20, 2):
        t.insert(i, str(i))
    assert [k for k, _ in t.next_k(4, 3)] == [6, 8, 10]
    assert [k for k, _ in t.next_k(5, 3)] == [6, 8, 10]
    assert [k for k, _ in t.next_k(16, 5)] == [18]
    assert list(t.next_k(-1, 0)) == []


def test_tuple_keys_break_ties():
    """Key = (start, event id): two events at 16:00 don't collide (plan 6.2)."""
    t = AVLTree()
    t.insert((1600, 2), "b")
    t.insert((1600, 1), "a")
    assert [v for _, v in t.next_k((1600, 0), 5)] == ["a", "b"]


def test_check_detects_broken_invariants():
    t = AVLTree()
    for i in range(7):
        t.insert(i, i)
    t.root.height += 1
    with pytest.raises(AssertionError):
        t.check()
    t.root.height -= 1
    t.root.left.key, t.root.right.key = t.root.right.key, t.root.left.key
    with pytest.raises(AssertionError):
        t.check()


def test_avl_matches_brute_force():
    rng = random.Random(42)  # fixed seed: failures are reproducible
    t, naive = AVLTree(), {}  # dict allowed in tests only
    for step in range(5000):
        k = rng.randrange(0, 1000)
        r = rng.random()
        if r < 0.6:
            t.insert(k, step)
            naive[k] = step
        elif r < 0.9:
            if k in naive:
                t.delete(k)
                del naive[k]
            else:
                with pytest.raises(KeyError):
                    t.delete(k)
        else:
            if k in naive:
                assert t.find(k) == naive[k]
            else:
                with pytest.raises(KeyError):
                    t.find(k)
        t.check()  # invariants after EVERY operation
        assert len(t) == len(naive)

        lo = rng.randrange(0, 1000)
        hi = lo + rng.randrange(0, 200)
        assert list(t.range(lo, hi)) == sorted((x, v) for x, v in naive.items() if lo <= x <= hi)

        after, want = rng.randrange(-1, 1000), rng.randrange(0, 8)
        assert list(t.next_k(after, want)) == sorted((x, v) for x, v in naive.items() if x > after)[:want]

    assert [k for k in t.in_order()] == sorted(naive)
