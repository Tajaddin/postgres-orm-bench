"""``orm-bench`` CLI."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from orm_bench import IMPLS, Workload, run_all


@click.command()
@click.option("--dsn", default=None, help="DB DSN. Defaults to sqlite:///./bench.sqlite or $ORM_BENCH_DSN.")
@click.option("--records", type=int, default=5_000)
@click.option("--orders-per-product", type=int, default=5)
@click.option("--users", type=int, default=200)
@click.option("--iter", "n_iter", type=int, default=3)
@click.option("--out", default="bench/results.json")
def main(dsn, records, orders_per_product, users, n_iter, out):
    """Run all 4 implementations on the workload + write a JSON report."""
    dsn = dsn or os.environ.get("ORM_BENCH_DSN", "sqlite:///./bench.sqlite")
    w = Workload(
        n_records=records, n_orders_per_product=orders_per_product, n_users=users, n_iter=n_iter
    )
    click.echo(f"DSN: {dsn}")
    click.echo(f"Workload: {w}\n")
    results = run_all(IMPLS, dsn, w)

    summary = {"dsn": dsn, "workload": w.__dict__, "results": []}
    for r in results:
        summary["results"].append(
            {
                "impl": r.impl_name,
                "op": r.op,
                "n": r.n,
                "seconds": round(r.seconds, 4),
                "ops_per_sec": r.ops_per_sec,
                "rows": r.rows,
            }
        )
    code_lines = {impl.name: impl.code_line_count for impl in IMPLS}
    summary["impl_code_lines"] = code_lines

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    click.echo(json.dumps(summary, indent=2))
    click.echo(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
