"""Queue (circular buffer, plan section 7.2): randomised against collections.deque."""

import random
from collections import deque

import pytest

from app.ds import Queue


def test_empty_queue_raises():
    q = Queue()
    assert len(q) == 0 and q.is_empty()
    with pytest.raises(IndexError):
        q.dequeue()
    with pytest.raises(IndexError):
        q.peek()


def test_fifo_order_across_growth():
    q = Queue()
    for i in range(100):
        q.enqueue(i)
    assert len(q) == 100 and q.peek() == 0
    assert [q.dequeue() for _ in range(100)] == list(range(100))
    assert q.is_empty()


def test_wraparound_then_resize_keeps_order():
    q = Queue()
    for i in range(4):
        q.enqueue(i)
    q.dequeue()
    q.dequeue()
    for i in range(4, 10):  # tail wraps past the end, then the buffer doubles
        q.enqueue(i)
    assert [q.dequeue() for _ in range(len(q))] == list(range(2, 10))


def test_holds_none():
    q = Queue()
    q.enqueue(None)
    q.enqueue(1)
    assert q.dequeue() is None and q.dequeue() == 1


def test_queue_matches_deque():
    rng = random.Random(42)
    q, naive = Queue(), deque()
    for step in range(20000):
        if rng.random() < 0.55:
            q.enqueue(step)
            naive.append(step)
        elif naive:
            assert q.dequeue() == naive.popleft()
        else:
            with pytest.raises(IndexError):
                q.dequeue()
        assert len(q) == len(naive)
        assert q.is_empty() == (not naive)
        if naive:
            assert q.peek() == naive[0]
