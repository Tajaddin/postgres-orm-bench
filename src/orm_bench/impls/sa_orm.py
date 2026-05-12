"""SQLAlchemy 2.0 ORM (declarative)."""

from __future__ import annotations

import random
from pathlib import Path

from sqlalchemy import ForeignKey, Integer, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class _Base(DeclarativeBase):
    pass


class User(_Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class Product(_Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class Order(_Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)


class SaOrmImpl:
    name = "sqlalchemy_orm"
    code_line_count = 0  # filled in after import; the line count of THIS file

    def __init__(self) -> None:
        self.engine = None
        self._session: Session | None = None
        self.code_line_count = _count_lines(__file__)

    def setup(self, dsn: str) -> None:
        ca = {"check_same_thread": False} if dsn.startswith("sqlite") else {}
        self.engine = create_engine(dsn, connect_args=ca, future=True)
        _Base.metadata.drop_all(self.engine)
        _Base.metadata.create_all(self.engine)
        self._session = Session(self.engine, future=True)

    def reset(self) -> None:
        assert self._session is not None
        s = self._session
        s.query(Order).delete()
        s.query(Product).delete()
        s.query(User).delete()
        s.commit()

    def bulk_insert(self, w) -> int:
        assert self._session is not None
        s = self._session
        users = [User(name=f"user{i}") for i in range(w.n_users)]
        s.add_all(users)
        s.flush()
        products = [
            Product(name=f"p{i}", price_cents=100 + (i * 7) % 1000)
            for i in range(w.n_records)
        ]
        s.add_all(products)
        s.flush()
        orders = []
        rnd = random.Random(42)
        for p in products:
            for _ in range(w.n_orders_per_product):
                orders.append(
                    Order(
                        user_id=rnd.choice(users).id,
                        product_id=p.id,
                        quantity=rnd.randint(1, 5),
                    )
                )
        s.add_all(orders)
        s.commit()
        return len(orders) + len(products) + len(users)

    def single_lookup(self, n: int) -> int:
        assert self._session is not None
        s = self._session
        rnd = random.Random(0)
        max_id = s.execute(select(func.max(Product.id))).scalar() or 1
        ids = [rnd.randint(1, max_id) for _ in range(n)]
        hits = 0
        for pid in ids:
            p = s.get(Product, pid)
            if p is not None:
                hits += 1
        return hits

    def indexed_filter(self, n: int) -> int:
        assert self._session is not None
        s = self._session
        rnd = random.Random(0)
        max_uid = s.execute(select(func.max(User.id))).scalar() or 1
        total = 0
        for _ in range(n):
            uid = rnd.randint(1, max_uid)
            total += s.execute(
                select(func.count()).where(Order.user_id == uid)
            ).scalar_one()
        return total

    def complex_join(self, n: int) -> int:
        assert self._session is not None
        s = self._session
        rows = s.execute(
            select(
                User.id,
                func.sum(Order.quantity * Product.price_cents).label("spend"),
            )
            .join(Order, Order.user_id == User.id)
            .join(Product, Product.id == Order.product_id)
            .group_by(User.id)
        ).all()
        return len(rows)

    def teardown(self) -> None:
        if self._session is not None:
            self._session.close()
        if self.engine is not None:
            self.engine.dispose()


def _count_lines(path: str) -> int:
    return sum(
        1 for ln in Path(path).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
