"""Smoke test: every structure is importable from app.ds. Real randomised tests go next to this."""

from app import ds


def test_all_structures_exported():
    for name in ["HashMap", "Queue", "IndexedMinHeap", "AVLTree", "IntervalTree", "Graph", "DynamicArray"]:
        assert hasattr(ds, name), name
