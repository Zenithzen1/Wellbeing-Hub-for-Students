"""Benchmarks for the report (plan section 12): the booking structures against the naive alternative.

    python bench/bench_booking.py            (from backend/; ~1 minute)
    python bench/bench_booking.py --quick    (smaller sizes, a few seconds)

1. Overlap query, "is [s, e) free?": IntervalTree.find_overlap vs scanning a list of bookings.
2. All overlaps in a window (the day grid): IntervalTree.query vs filtering the list.
3. Leaving the waitlist: IndexedMinHeap.remove(id) vs a heapq list (search, delete, re-heapify).

For n = 10^2 .. 10^5 it times many random operations and reports the median microseconds per
operation. Writes bench/out/booking.csv, and bench/out/booking.png when matplotlib is installed
(pip install matplotlib). Owner: Aditya.
"""

import argparse
import csv
import heapq
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run from anywhere

from app.ds import IndexedMinHeap, IntervalTree  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
SEED = 2026


def per_op_us(fn, ops, repeats=5):
    """Median over `repeats` runs of (total time / ops), in microseconds."""
    runs = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        runs.append((time.perf_counter() - t0) / ops * 1e6)
    return statistics.median(runs)


def bookings(n, rng):
    """n non-overlapping half-open sessions [s, e) on a timeline, in random order, like a
    counsellor's busy intervals. Times are minutes; gaps of 0-60 minutes between sessions."""
    out, t = [], 0
    for _ in range(n):
        t += rng.randrange(0, 61)
        length = rng.choice((45, 60))
        out.append((t, t + length))
        t += length
    rng.shuffle(out)
    return out, t


def bench_overlap(n, rng, queries):
    items, horizon = bookings(n, rng)
    tree = IntervalTree()
    for s, e in items:
        tree.insert(s, e - 1)  # half-open [s, e) stored closed, as services/booking.py does
    qs = [(q, q + 45) for q in (rng.randrange(0, horizon) for _ in range(queries))]
    windows = [(q, q + 8 * 60) for q in (rng.randrange(0, horizon) for _ in range(queries))]

    def tree_any():
        for s, e in qs:
            tree.find_overlap(s, e - 1)

    def list_any():
        for s, e in qs:
            any(bs < e and s < be for bs, be in items)

    def tree_all():
        for s, e in windows:
            tree.query(s, e - 1)

    def list_all():
        for s, e in windows:
            sorted((bs, be) for bs, be in items if bs < e and s < be)

    # The two methods must agree before their timings mean anything.
    for s, e in qs[:50]:
        assert (tree.find_overlap(s, e - 1) is not None) == any(bs < e and s < be for bs, be in items)
    for s, e in windows[:20]:
        assert [(a, b + 1) for a, b in tree.query(s, e - 1)] == sorted(
            (bs, be) for bs, be in items if bs < e and s < be)

    return {
        "overlap_tree_us": per_op_us(tree_any, len(qs)),
        "overlap_list_us": per_op_us(list_any, len(qs)),
        "day_tree_us": per_op_us(tree_all, len(windows)),
        "day_list_us": per_op_us(list_all, len(windows)),
    }


def bench_remove(n, rng, removals):
    """Each run: build the line of n students, then `removals` of them leave."""
    keys = [((rng.randrange(2), rng.random(), i), i) for i in range(n)]  # ((tier, joined, id), id)
    leaving = rng.sample(range(n), removals)

    def indexed():
        heap = IndexedMinHeap()
        heap.build_heap([(i, k) for k, i in keys])
        t0 = time.perf_counter()
        for i in leaving:
            heap.remove(i)
        return time.perf_counter() - t0

    def plain():
        heap = list(keys)
        heapq.heapify(heap)
        t0 = time.perf_counter()
        for i in leaving:
            idx = next(j for j, (_, x) in enumerate(heap) if x == i)  # O(n) search
            heap[idx] = heap[-1]
            heap.pop()
            heapq.heapify(heap)                                          # O(n) repair
        return time.perf_counter() - t0

    def median_us(fn):
        return statistics.median(fn() for _ in range(3)) / removals * 1e6

    return {"remove_indexed_us": median_us(indexed), "remove_list_us": median_us(plain)}


def plot(rows, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed: skipped the plot (pip install matplotlib)")
        return
    ns = [r["n"] for r in rows]
    panels = [
        ("Is [s, e) free? (overlap check)", "overlap_tree_us", "overlap_list_us", "IntervalTree.find_overlap"),
        ("Busy intervals in an 8-hour window", "day_tree_us", "day_list_us", "IntervalTree.query"),
        ("A student leaves the waitlist", "remove_indexed_us", "remove_list_us", "IndexedMinHeap.remove"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
    for ax, (title, ours, naive, label) in zip(axes, panels):
        ax.loglog(ns, [r[ours] for r in rows], "o-", label=label, color="#1F4D46", linewidth=2)
        ax.loglog(ns, [r[naive] for r in rows], "s--", label="plain list", color="#9F2D20", linewidth=2)
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("n (intervals or waitlist entries)")
        ax.set_ylabel("µs per operation (median)")
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    print(f"wrote {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="n up to 10^4 only")
    args = parser.parse_args()
    sizes = [100, 1_000, 10_000] if args.quick else [100, 1_000, 10_000, 100_000]

    rng = random.Random(SEED)
    rows = []
    for n in sizes:
        ops = max(20, min(1_000, 2_000_000 // n))  # keep the list baselines bearable at 10^5
        row = {"n": n, **bench_overlap(n, rng, ops), **bench_remove(n, rng, min(ops, n // 2))}
        rows.append(row)
        print(f"n={n:>7,}  overlap tree {row['overlap_tree_us']:8.2f} us  list {row['overlap_list_us']:10.2f} us"
              f" | window tree {row['day_tree_us']:8.2f} us  list {row['day_list_us']:10.2f} us"
              f" | remove heap {row['remove_indexed_us']:7.2f} us  list {row['remove_list_us']:10.2f} us")

    OUT.mkdir(exist_ok=True)
    with open(OUT / "booking.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT / 'booking.csv'}")
    plot(rows, OUT / "booking.png")


if __name__ == "__main__":
    main()
