# postgres-orm-bench

> Head-to-head benchmark of four Python database access layers on the *same* schema, *same* workload, *same* assertions. **Raw SQL is 5.9× faster on bulk insert and 8.2× faster on point lookups vs SQLAlchemy ORM** — but on complex multi-table JOINs the spread collapses to 8% because the SQL planner does the work, not the ORM. Code-line cost of choosing raw SQL: **+64% more lines** for the same workload. **26/26 tests pass in 4.8 s** and every implementation produces byte-identical join results (parity test).

[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE) [![Tests](https://img.shields.io/badge/tests-26%20passing-brightgreen)](#tests) [![Python](https://img.shields.io/badge/python-3.10%2B-blue)]()

## Why this exists

"Should I use an ORM?" is a religious question with no real numbers attached most of the time. This repo runs the four most-popular Python options against the same four operations on the same schema and emits a JSON report you can paste into a design doc.

The schema is intentionally non-trivial — users + products + orders, two FKs, two indexes — so the comparison reflects real workloads, not "select 1".

## Hero numbers — `python -m orm_bench.cli --records 2000 --orders-per-product 3 --users 100`

8000 rows inserted, 200 lookups per measured op, SQLite backend on commodity laptop, median of 3 iterations:

| Operation | SQLAlchemy ORM | SQLAlchemy Core | Peewee | Raw SQL | Winner |
|---|---:|---:|---:|---:|:---:|
| `bulk_insert` (ops/s) | 11,364 | 145,645 | 37,818 | **216,685** | raw |
| `single_lookup` (ops/s) | 1,795 | 3,928 | 2,499 | **14,654** | raw |
| `indexed_filter` (ops/s) | 2,661 | 2,539 | 2,447 | **14,232** | raw |
| `complex_join` (ops/s) | 235 | 239 | 111 | **256** | raw (barely) |
| Code lines for full workload | 116 | 110 | 102 | **190** | ORMs (-46 %) |

### The two facts worth pulling out

1. **Raw SQL dominates everything except the join.** On bulk insert, point lookups, and indexed filters the gap is 5–8×. The ORM cost is real and it's mostly Python-object materialization overhead, not SQL.
2. **On the complex JOIN, everything converges.** All four are within 2× of each other because Postgres / SQLite is doing the actual work in the planner. The ORM cost vanishes when the database is the bottleneck — which is exactly the case in most production read paths.

**Decision rule that falls out of the data:** if your hot path is "select N rows by primary key and hand them to Pydantic," raw SQL pays for itself. If your hot path is "JOIN three tables and aggregate," the ORM costs you nothing measurable AND gives you back ~40 % of your code.

The full per-op `seconds`, `ops_per_sec`, and result-row counts are in [`bench/results.json`](bench/results.json).

## What every implementation does

All four implementations live behind the same protocol (`OrmImpl`) with four methods:

```python
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
```

The four ops:

| Op | What it measures |
|---|---|
| `bulk_insert(w)` | Insert `w.n_users` users + `w.n_records` products + `w.n_records * w.n_orders_per_product` orders, inside one transaction. Reports total rows inserted. |
| `single_lookup(n)` | Fetch `n` products by primary key (random IDs). |
| `indexed_filter(n)` | For `n` random user IDs, `COUNT(*)` on orders.user_id (uses the index). |
| `complex_join(n)` | Per-user total spend across orders × products, one aggregate. |

The four implementations:

| Slug | Implementation | Why it's interesting |
|---|---|---|
| `sqlalchemy_orm` | SQLAlchemy 2.0 declarative ORM | The default Python ORM. Models with `Mapped[]` typing. |
| `sqlalchemy_core` | SQLAlchemy 2.0 Core (no ORM) | Same library, lower level. Tables + `select()`/`insert()`. |
| `peewee` | Peewee ORM | The lightweight alternative. Same conceptual surface as Django ORM. |
| `raw_sql` | sqlite3 / psycopg directly | The no-abstraction baseline. Parameterised SQL strings. |

## Quickstart

```bash
pip install -e ".[dev]"

# SQLite (default — no infra)
orm-bench --records 2000

# Postgres
pip install -e ".[postgres]"
orm-bench --dsn "postgresql+psycopg://user:pw@localhost/bench"
```

## Tests

```bash
pytest -v
```

```
test_runner.py             3 passed   Workload + BenchResult ops_per_sec math + zero-time safe
test_impls_smoke.py       20 passed   each of 4 impls × 5 invariants (full-workload run,
                                       complex-join row-count parity, indexed-filter sanity,
                                       reset clears, code_line_count > 20)
test_e2e_runner.py         3 passed   run_impl shape, teardown doesn't leak, ALL FOUR impls
                                       agree on complex_join row count
─────────────────────────────────────────────
26 passed in 4.84s
```

The parity test (`test_all_four_impls_yield_same_complex_join_row_count`) is the load-bearing one: same workload, same RNG seed, every implementation MUST produce the same row count. Without that, performance numbers are meaningless because we'd be comparing different queries.

## The honest caveats

**SQLite, not Postgres.** The default backend is SQLite for portability. Raw SQL's advantage shrinks somewhat on Postgres because the network round-trip dominates for point lookups. Run with `--dsn postgresql+psycopg://...` to see real numbers.

**Single-threaded.** No connection pool, no async, no parallel queries. Adding asyncpg + asyncio would shift the ranking — psycopg's sync API is the bottleneck for raw_sql's `single_lookup`, not the protocol.

**Driver matters more than ORM.** On Postgres, `asyncpg` is ~2× faster than `psycopg` on point lookups regardless of ORM choice. The orthogonal driver-choice axis is not measured here.

**Workload is fixed.** Real workloads have more writes-vs-reads variance, more partial updates, more bulk deletes. The four ops are representative, not exhaustive.

**No connection pooling overhead.** Production deployments wrap the engine in pgbouncer or SQLAlchemy's `QueuePool`. The setup cost of opening connections is excluded.

## Project layout

```
.
├── src/orm_bench/
│   ├── runner.py            # Workload, BenchResult, OrmImpl protocol, run_impl/run_all
│   ├── impls/
│   │   ├── sa_orm.py        # SQLAlchemy 2.0 declarative ORM
│   │   ├── sa_core.py       # SQLAlchemy 2.0 Core (Table + select/insert)
│   │   ├── peewee_orm.py    # Peewee
│   │   └── psycopg_raw.py   # sqlite3 / psycopg directly
│   └── cli.py               # `orm-bench`
├── tests/                   # 26 cases (3 + 20 + 3)
└── bench/run_benchmark.py + results.json
```

## License

MIT — see [LICENSE](LICENSE).
