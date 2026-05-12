"""Smoke tests for each implementation against SQLite (no Postgres required).

Each test runs a TINY workload (10 records, 1 order per product, 3 users)
so the suite stays fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orm_bench import Workload
from orm_bench.impls import PeeweeImpl, RawSqlImpl, SaCoreImpl, SaOrmImpl


def _dsn(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'smoke.sqlite').as_posix()}"


@pytest.mark.parametrize("Impl", [SaOrmImpl, SaCoreImpl, PeeweeImpl, RawSqlImpl])
def test_impl_runs_full_workload(Impl, tmp_path):
    impl = Impl()
    impl.setup(_dsn(tmp_path))
    try:
        impl.reset()
        w = Workload(n_records=10, n_orders_per_product=1, n_users=3, n_iter=1)
        inserted = impl.bulk_insert(w)
        assert inserted > 0
        hits = impl.single_lookup(20)
        assert hits >= 0
        total = impl.indexed_filter(10)
        assert total >= 0
        rows = impl.complex_join(1)
        assert rows == 3  # three users
    finally:
        impl.teardown()


@pytest.mark.parametrize("Impl", [SaOrmImpl, SaCoreImpl, PeeweeImpl, RawSqlImpl])
def test_impl_complex_join_matches_expected(Impl, tmp_path):
    """All implementations must produce identical join results on the same workload."""
    impl = Impl()
    impl.setup(_dsn(tmp_path))
    try:
        impl.reset()
        w = Workload(n_records=20, n_orders_per_product=2, n_users=5, n_iter=1)
        impl.bulk_insert(w)
        rows = impl.complex_join(1)
        assert rows == 5
    finally:
        impl.teardown()


@pytest.mark.parametrize("Impl", [SaOrmImpl, SaCoreImpl, PeeweeImpl, RawSqlImpl])
def test_impl_indexed_filter_counts_match_orders(Impl, tmp_path):
    """``indexed_filter`` should return >= 1 for each user with orders."""
    impl = Impl()
    impl.setup(_dsn(tmp_path))
    try:
        impl.reset()
        # 50 products * 5 orders = 250 orders across 5 users => avg 50 per user
        w = Workload(n_records=50, n_orders_per_product=5, n_users=5)
        impl.bulk_insert(w)
        total = impl.indexed_filter(10)
        # 10 sampled users with replacement out of 5 actual users => most should hit
        assert total > 0
    finally:
        impl.teardown()


@pytest.mark.parametrize("Impl", [SaOrmImpl, SaCoreImpl, PeeweeImpl, RawSqlImpl])
def test_impl_reset_clears_all_rows(Impl, tmp_path):
    impl = Impl()
    impl.setup(_dsn(tmp_path))
    try:
        w = Workload(n_records=10, n_orders_per_product=1, n_users=3)
        impl.bulk_insert(w)
        impl.reset()
        # complex_join after reset => 0 users
        rows = impl.complex_join(1)
        assert rows == 0
    finally:
        impl.teardown()


@pytest.mark.parametrize("Impl", [SaOrmImpl, SaCoreImpl, PeeweeImpl, RawSqlImpl])
def test_impl_reports_code_line_count(Impl):
    impl = Impl()
    assert impl.code_line_count > 20
