"""End-to-end: drive ``run_impl`` and assert the shape of the BenchResult list."""

from __future__ import annotations

from pathlib import Path

from orm_bench import IMPLS, Workload, run_impl


def test_run_impl_returns_four_results_in_canonical_order(tmp_path):
    dsn = f"sqlite:///{(tmp_path / 'e2e.sqlite').as_posix()}"
    impl = IMPLS[0]
    w = Workload(n_records=10, n_orders_per_product=1, n_users=3, n_iter=1)
    out = run_impl(impl, dsn, w)
    assert [r.op for r in out] == [
        "bulk_insert", "single_lookup", "indexed_filter", "complex_join",
    ]
    assert all(r.impl_name == impl.name for r in out)
    assert all(r.seconds >= 0 for r in out)


def test_run_impl_does_not_leak_db_after_teardown(tmp_path):
    dsn = f"sqlite:///{(tmp_path / 'cleanup.sqlite').as_posix()}"
    impl = IMPLS[0]
    w = Workload(n_records=5, n_orders_per_product=1, n_users=2, n_iter=1)
    out = run_impl(impl, dsn, w)
    assert out  # ran something
    # The teardown closed the connection; re-running setup must succeed.
    impl.setup(dsn)
    impl.reset()
    impl.teardown()


def test_all_four_impls_yield_same_complex_join_row_count(tmp_path):
    """Strong correctness invariant — every implementation, same data, same result."""
    dsn = f"sqlite:///{(tmp_path / 'parity.sqlite').as_posix()}"
    w = Workload(n_records=30, n_orders_per_product=3, n_users=7, n_iter=1)
    counts = {}
    for impl in IMPLS:
        out = run_impl(impl, dsn, w)
        cj = next(r for r in out if r.op == "complex_join")
        counts[impl.name] = cj.rows
    assert len(set(counts.values())) == 1, f"impls disagree: {counts}"
