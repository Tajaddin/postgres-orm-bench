"""Tests for the runner + Workload + BenchResult."""

from __future__ import annotations

from orm_bench import BenchResult, Workload


def test_workload_defaults_are_reasonable():
    w = Workload()
    assert w.n_records > 0
    assert w.n_orders_per_product > 0
    assert w.n_users > 0


def test_bench_result_computes_ops_per_sec():
    r = BenchResult(impl_name="x", op="bulk_insert", n=10_000, seconds=2.0)
    assert r.ops_per_sec == 5000.0


def test_bench_result_zero_time_is_safe():
    r = BenchResult(impl_name="x", op="bulk_insert", n=10, seconds=0.0)
    assert r.ops_per_sec == 0.0
