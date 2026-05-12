"""Benchmark runner.

Each implementation exposes the same four operations:

1. ``bulk_insert(n)``  — insert n products + 5n orders
2. ``single_lookup(n)`` — fetch n random products by id
3. ``indexed_filter(n)`` — orders by user_id (uses index)
4. ``complex_join(n)`` — per-user total spend (orders × products aggregation)

The runner clears the schema, runs each op once for warm-up, then measures
``n_iter`` repetitions. Latency is wall-time per operation.
"""

from __future__ import annotations

import gc
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol


@dataclass
class Workload:
    n_records: int = 5_000           # products
    n_orders_per_product: int = 5    # orders
    n_users: int = 200
    n_iter: int = 3                  # repeats per op for averaging


@dataclass
class BenchResult:
    impl_name: str
    op: str
    n: int
    seconds: float
    rows: int = 0
    ops_per_sec: float = 0.0

    def __post_init__(self) -> None:
        if self.seconds > 0:
            self.ops_per_sec = round(self.n / self.seconds, 1)


class OrmImpl(Protocol):
    name: str
    code_line_count: int

    def setup(self, dsn: str) -> None: ...
    def reset(self) -> None: ...
    def bulk_insert(self, w: Workload) -> int: ...
    def single_lookup(self, n: int) -> int: ...
    def indexed_filter(self, n: int) -> int: ...
    def complex_join(self, n: int) -> int: ...
    def teardown(self) -> None: ...


def _time_call(fn: Callable[[], int], iters: int) -> tuple[float, int]:
    """Run ``fn`` ``iters`` times, return (median_seconds, last_rows)."""
    times: list[float] = []
    rows = 0
    for _ in range(iters):
        gc.collect()
        t0 = time.perf_counter()
        rows = fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times), rows


def run_impl(impl: OrmImpl, dsn: str, w: Workload) -> list[BenchResult]:
    impl.setup(dsn)
    out: list[BenchResult] = []
    try:
        # 1. Bulk insert (reset before so each run starts clean)
        impl.reset()
        t, rows = _time_call(
            lambda: impl.bulk_insert(w),
            iters=1,  # bulk insert is destructive; run once
        )
        n_inserted = w.n_records * (1 + w.n_orders_per_product)
        out.append(BenchResult(impl.name, "bulk_insert", n_inserted, t, rows))

        # 2. Single-row lookup (n=200 random ids)
        t, rows = _time_call(lambda: impl.single_lookup(200), iters=w.n_iter)
        out.append(BenchResult(impl.name, "single_lookup", 200, t, rows))

        # 3. Indexed filter
        t, rows = _time_call(lambda: impl.indexed_filter(200), iters=w.n_iter)
        out.append(BenchResult(impl.name, "indexed_filter", 200, t, rows))

        # 4. Complex join (one aggregate over all rows)
        t, rows = _time_call(lambda: impl.complex_join(1), iters=w.n_iter)
        out.append(BenchResult(impl.name, "complex_join", 1, t, rows))
    finally:
        impl.teardown()
    return out


def run_all(impls: list[OrmImpl], dsn: str, w: Workload) -> list[BenchResult]:
    all_results: list[BenchResult] = []
    for impl in impls:
        all_results.extend(run_impl(impl, dsn, w))
    return all_results


def _default_dsn() -> str:
    return os.environ.get("ORM_BENCH_DSN", "sqlite:///./bench.sqlite")
