"""Peewee ORM."""

from __future__ import annotations

import random
from pathlib import Path

import peewee as pw


_db = pw.DatabaseProxy()


class _Base(pw.Model):
    class Meta:
        database = _db


class User(_Base):
    name = pw.CharField(max_length=50)


class Product(_Base):
    name = pw.CharField(max_length=50)
    price_cents = pw.IntegerField()


class Order(_Base):
    user = pw.ForeignKeyField(User, backref="orders", index=True)
    product = pw.ForeignKeyField(Product, backref="orders", index=True)
    quantity = pw.IntegerField()


class PeeweeImpl:
    name = "peewee"

    def __init__(self) -> None:
        self.code_line_count = _count_lines(__file__)

    def setup(self, dsn: str) -> None:
        if dsn.startswith("sqlite"):
            path = dsn.removeprefix("sqlite:///")
            _db.initialize(pw.SqliteDatabase(path))
        else:
            # postgres://user:pass@host/db
            import urllib.parse

            u = urllib.parse.urlparse(dsn)
            _db.initialize(
                pw.PostgresqlDatabase(
                    u.path.lstrip("/"),
                    user=u.username,
                    password=u.password,
                    host=u.hostname,
                    port=u.port or 5432,
                )
            )
        _db.connect(reuse_if_open=True)
        _db.drop_tables([Order, Product, User], safe=True)
        _db.create_tables([User, Product, Order])

    def reset(self) -> None:
        Order.delete().execute()
        Product.delete().execute()
        User.delete().execute()

    def bulk_insert(self, w) -> int:
        rnd = random.Random(42)
        with _db.atomic():
            User.insert_many(
                [{"name": f"user{i}"} for i in range(w.n_users)]
            ).execute()
            Product.insert_many(
                [{"name": f"p{i}", "price_cents": 100 + (i * 7) % 1000} for i in range(w.n_records)]
            ).execute()
            user_ids = [u.id for u in User.select(User.id)]
            product_ids = [p.id for p in Product.select(Product.id)]
            order_rows = []
            for pid in product_ids:
                for _ in range(w.n_orders_per_product):
                    order_rows.append(
                        {"user": rnd.choice(user_ids), "product": pid, "quantity": rnd.randint(1, 5)}
                    )
            Order.insert_many(order_rows).execute()
        return len(order_rows) + len(product_ids) + len(user_ids)

    def single_lookup(self, n: int) -> int:
        rnd = random.Random(0)
        max_id = Product.select(pw.fn.MAX(Product.id)).scalar() or 1
        hits = 0
        for _ in range(n):
            pid = rnd.randint(1, max_id)
            if Product.get_or_none(Product.id == pid) is not None:
                hits += 1
        return hits

    def indexed_filter(self, n: int) -> int:
        rnd = random.Random(0)
        max_uid = User.select(pw.fn.MAX(User.id)).scalar() or 1
        total = 0
        for _ in range(n):
            uid = rnd.randint(1, max_uid)
            total += Order.select().where(Order.user == uid).count()
        return total

    def complex_join(self, n: int) -> int:
        q = (
            User.select(
                User.id,
                pw.fn.SUM(Order.quantity * Product.price_cents).alias("spend"),
            )
            .join(Order, on=(Order.user == User.id))
            .join(Product, on=(Product.id == Order.product))
            .group_by(User.id)
        )
        return len(list(q))

    def teardown(self) -> None:
        try:
            _db.close()
        except Exception:  # noqa: BLE001
            pass


def _count_lines(path: str) -> int:
    return sum(
        1 for ln in Path(path).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
