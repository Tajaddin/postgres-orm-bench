"""SQLAlchemy 2.0 Core (no ORM, low-level)."""

from __future__ import annotations

import random
from pathlib import Path

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
)


def _sa_dsn(dsn: str) -> str:
    """Map a generic postgres DSN to SQLAlchemy's psycopg (v3) dialect, since
    this project ships psycopg[binary] (v3), not psycopg2."""
    for prefix in ("postgresql://", "postgres://"):
        if dsn.startswith(prefix):
            return "postgresql+psycopg://" + dsn[len(prefix):]
    return dsn


_meta = MetaData()

_users = Table(
    "users", _meta,
    Column("id", Integer, primary_key=True),
    Column("name", String(50), nullable=False),
)
_products = Table(
    "products", _meta,
    Column("id", Integer, primary_key=True),
    Column("name", String(50), nullable=False),
    Column("price_cents", Integer, nullable=False),
)
_orders = Table(
    "orders", _meta,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id"), nullable=False, index=True),
    Column("product_id", Integer, ForeignKey("products.id"), nullable=False, index=True),
    Column("quantity", Integer, nullable=False),
)


class SaCoreImpl:
    name = "sqlalchemy_core"

    def __init__(self) -> None:
        self.engine = None
        self.code_line_count = _count_lines(__file__)

    def setup(self, dsn: str) -> None:
        ca = {"check_same_thread": False} if dsn.startswith("sqlite") else {}
        self.engine = create_engine(_sa_dsn(dsn), connect_args=ca, future=True)
        _meta.drop_all(self.engine)
        _meta.create_all(self.engine)

    def reset(self) -> None:
        with self.engine.begin() as c:
            c.execute(_orders.delete())
            c.execute(_products.delete())
            c.execute(_users.delete())

    def bulk_insert(self, w) -> int:
        rnd = random.Random(42)
        with self.engine.begin() as c:
            c.execute(insert(_users), [{"name": f"user{i}"} for i in range(w.n_users)])
            c.execute(
                insert(_products),
                [{"name": f"p{i}", "price_cents": 100 + (i * 7) % 1000} for i in range(w.n_records)],
            )
            user_ids = [r[0] for r in c.execute(select(_users.c.id))]
            product_ids = [r[0] for r in c.execute(select(_products.c.id))]
            orders = []
            for pid in product_ids:
                for _ in range(w.n_orders_per_product):
                    orders.append(
                        {"user_id": rnd.choice(user_ids), "product_id": pid, "quantity": rnd.randint(1, 5)}
                    )
            c.execute(insert(_orders), orders)
            return len(orders) + len(product_ids) + len(user_ids)

    def single_lookup(self, n: int) -> int:
        rnd = random.Random(0)
        with self.engine.connect() as c:
            max_id = c.execute(select(func.max(_products.c.id))).scalar() or 1
            hits = 0
            for _ in range(n):
                pid = rnd.randint(1, max_id)
                row = c.execute(select(_products).where(_products.c.id == pid)).first()
                if row is not None:
                    hits += 1
        return hits

    def indexed_filter(self, n: int) -> int:
        rnd = random.Random(0)
        total = 0
        with self.engine.connect() as c:
            max_uid = c.execute(select(func.max(_users.c.id))).scalar() or 1
            for _ in range(n):
                uid = rnd.randint(1, max_uid)
                total += c.execute(
                    select(func.count()).where(_orders.c.user_id == uid)
                ).scalar_one()
        return total

    def complex_join(self, n: int) -> int:
        with self.engine.connect() as c:
            rows = c.execute(
                select(
                    _users.c.id,
                    func.sum(_orders.c.quantity * _products.c.price_cents).label("spend"),
                )
                .join(_orders, _orders.c.user_id == _users.c.id)
                .join(_products, _products.c.id == _orders.c.product_id)
                .group_by(_users.c.id)
            ).all()
        return len(rows)

    def teardown(self) -> None:
        if self.engine is not None:
            self.engine.dispose()


def _count_lines(path: str) -> int:
    return sum(
        1 for ln in Path(path).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
