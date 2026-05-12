"""postgres-orm-bench — head-to-head DB access benchmark.

Exports:

* :class:`Workload` — pure-data spec of what to benchmark
* :class:`OrmImpl` Protocol + four implementations under ``impls/``
* :class:`BenchResult` — one (impl, op) data point
* :func:`run_all` — executes the cartesian product
"""

from orm_bench.impls import IMPLS
from orm_bench.runner import BenchResult, OrmImpl, Workload, run_all, run_impl

__all__ = ["BenchResult", "IMPLS", "OrmImpl", "Workload", "run_all", "run_impl"]
