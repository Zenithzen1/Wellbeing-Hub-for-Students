"""IntervalTree (AVL + max end per node): randomised against a plain list, plus the plan's worked example."""

import random

import pytest

from app.ds import IntervalTree


def check_max(tree):
    """AVL invariants plus: every node's maxHigh is the largest high in its subtree."""
    tree.check()

    def walk(node):
        if node is None:
            return None
        best = node.key[1]
        for child in (node.left, node.right):
            sub = walk(child)
            if sub is not None and sub > best:
                best = sub
        assert node.maxHigh == best, f"maxHigh {node.maxHigh} != {best} at {node.key}"
        return best

    walk(tree.root)


def overlaps(a, b):
    return a[0] <= b[1] and b[0] <= a[1]


def test_interval_tree_matches_brute_force():
    rng = random.Random(42)  # fixed seed: failures are reproducible
    tree, naive = IntervalTree(), {}
    for step in range(4000):
        if rng.random() < 0.65 or not naive:
            s = rng.randrange(0, 1000)
            e = s + rng.randrange(0, 60)
            tree.insert(s, e, step)
            naive[(s, e)] = step
        else:
            key = rng.choice(list(naive))
            tree.delete(*key)
            del naive[key]

        q = rng.randrange(0, 1000)
        qe = q + rng.randrange(0, 80)
        expected = sorted(k for k in naive if overlaps(k, (q, qe)))
        assert list(tree.query(q, qe)) == expected
        hit = tree.find_overlap(q, qe)
        if expected:
            assert hit is not None and overlaps(hit, (q, qe))
        else:
            assert hit is None
        assert len(tree) == len(naive)
        if step % 50 == 0:
            check_max(tree)
    check_max(tree)
    for key, value in naive.items():
        assert tree.search(key) == value


def test_sorted_inserts_stay_balanced_and_keep_max():
    tree = IntervalTree()
    for i in range(1024):
        tree.insert(i * 10, i * 10 + 5, i)
    check_max(tree)
    assert tree.height() <= 11  # perfectly balanced would be 11 for 1024 nodes; AVL keeps it tight
    for i in range(0, 1024, 2):
        tree.delete(i * 10, i * 10 + 5)
    check_max(tree)
    assert len(tree) == 512


def test_plan_worked_example_half_open_via_end_minus_one():
    """Dr Noor's Monday (plan section 4). Minutes since midnight; [s, e) is stored as (s, e - 1)."""

    def hm(h, m=0):
        return h * 60 + m

    tree = IntervalTree()
    for s, e in [(hm(9), hm(10)), (hm(10), hm(10, 45)), (hm(11), hm(12)), (hm(13), hm(13, 45)),
                 (hm(14), hm(15)), (hm(15, 30), hm(16, 15))]:
        tree.insert(s, e - 1)
    check_max(tree)
    assert tree.height() == 3
    assert tree.find_overlap(hm(11, 30), hm(12, 15) - 1) == (hm(11), hm(12) - 1)  # rejected
    assert tree.find_overlap(hm(12), hm(12, 45) - 1) is None                       # accepted
    assert tree.find_overlap(hm(10, 45), hm(11) - 1) is None                       # touching is fine


def test_bad_ranges_and_missing_keys():
    tree = IntervalTree()
    with pytest.raises(ValueError):
        tree.insert(5, 4)
    with pytest.raises(ValueError):
        tree.query(5, 4)
    with pytest.raises(KeyError):
        tree.delete(1, 2)
