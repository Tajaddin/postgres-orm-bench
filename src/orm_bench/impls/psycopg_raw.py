"""Raw SQL via psycopg (Postgres) OR sqlite3 (when DSN starts with ``sqlite``).

This is the no-ORM baseline. Same workload, but every query is a parameterized
SQL string the implementation runs against the driver directly.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (product_id) REFERENCES products(id)
);
CREATE INDEX IF NOT EXISTS ix_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS ix_orders_product ON orders(product_id);
"""


class RawSqlImpl:
    name = "raw_sql"

    def __init__(self) -> None:
        self.conn = None
        self.is_sqlite = True
        self.code_line_count = _count_lines(__file__)

    def setup(self, dsn: str) -> None:
        if dsn.startswith("sqlite"):
            self.is_sqlite = True
            path = dsn.removeprefix("sqlite:///")
            self.conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
            self.conn.executescript("DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS products; DROP TABLE IF EXISTS users;")
            self.conn.executescript(_SQLITE_SCHEMA)
        else:
            self.is_sqlite = False
            import psycopg

            self.conn = psycopg.connect(dsn, autocommit=True)
            with self.conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS orders CASCADE;")
                cur.execute("DROP TABLE IF EXISTS products CASCADE;")
                cur.execute("DROP TABLE IF EXISTS users CASCADE;")
                cur.execute(
                    """
                    CREATE TABLE users (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL);
                    CREATE TABLE products (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, price_cents INTEGER NOT NULL);
                    CREATE TABLE orders (
                        id BIGSERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(id),
                        product_id BIGINT NOT NULL REFERENCES products(id),
                        quantity INTEGER NOT NULL
                    );
                    CREATE INDEX ix_orders_user ON orders(user_id);
                    CREATE INDEX ix_orders_product ON orders(product_id);
                    """
                )

    def _ph(self) -> str:
        return "?" if self.is_sqlite else "%s"

    def reset(self) -> None:
        cur = self.conn.cursor() if not self.is_sqlite else self.conn
        if self.is_sqlite:
            self.conn.executescript("DELETE FROM orders; DELETE FROM products; DELETE FROM users;")
        else:
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM orders;")
                cur.execute("DELETE FROM products;")
                cur.execute("DELETE FROM users;")

    def bulk_insert(self, w) -> int:
        rnd = random.Random(42)
        ph = self._ph()
        if self.is_sqlite:
            cur = self.conn.cursor()
            cur.execute("BEGIN")
            try:
                cur.executemany(
                    f"INSERT INTO users (name) VALUES ({ph})",
                    [(f"user{i}",) for i in range(w.n_users)],
                )
                cur.executemany(
                    f"INSERT INTO products (name, price_cents) VALUES ({ph}, {ph})",
                    [(f"p{i}", 100 + (i * 7) % 1000) for i in range(w.n_records)],
                )
                user_ids = [r[0] for r in cur.execute("SELECT id FROM users")]
                product_ids = [r[0] for r in cur.execute("SELECT id FROM products")]
                rows = []
                for pid in product_ids:
                    for _ in range(w.n_orders_per_product):
                        rows.append((rnd.choice(user_ids), pid, rnd.randint(1, 5)))
                cur.executemany(
                    f"INSERT INTO orders (user_id, product_id, quantity) VALUES ({ph}, {ph}, {ph})",
                    rows,
                )
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise
        else:
            with self.conn.cursor() as cur:
                cur.executemany("INSERT INTO users (name) VALUES (%s)", [(f"user{i}",) for i in range(w.n_users)])
                cur.executemany(
                    "INSERT INTO products (name, price_cents) VALUES (%s, %s)",
                    [(f"p{i}", 100 + (i * 7) % 1000) for i in range(w.n_records)],
                )
                cur.execute("SELECT id FROM users")
                user_ids = [r[0] for r in cur.fetchall()]
                cur.execute("SELECT id FROM products")
                product_ids = [r[0] for r in cur.fetchall()]
                rows = []
                for pid in product_ids:
                    for _ in range(w.n_orders_per_product):
                        rows.append((rnd.choice(user_ids), pid, rnd.randint(1, 5)))
                cur.executemany(
                    "INSERT INTO orders (user_id, product_id, quantity) VALUES (%s, %s, %s)",
                    rows,
                )
        return w.n_users + w.n_records + (w.n_records * w.n_orders_per_product)

    def single_lookup(self, n: int) -> int:
        rnd = random.Random(0)
        ph = self._ph()
        cur = self.conn.cursor()
        if self.is_sqlite:
            max_id = cur.execute("SELECT COALESCE(MAX(id), 1) FROM products").fetchone()[0]
        else:
            with self.conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(id), 1) FROM products")
                max_id = cur.fetchone()[0]
        hits = 0
        for _ in range(n):
            pid = rnd.randint(1, max_id)
            if self.is_sqlite:
                row = self.conn.execute(f"SELECT id FROM products WHERE id = {ph}", (pid,)).fetchone()
            else:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT id FROM products WHERE id = %s", (pid,))
                    row = cur.fetchone()
            if row is not None:
                hits += 1
        return hits

    def indexed_filter(self, n: int) -> int:
        rnd = random.Random(0)
        ph = self._ph()
        if self.is_sqlite:
            max_uid = self.conn.execute("SELECT COALESCE(MAX(id), 1) FROM users").fetchone()[0]
        else:
            with self.conn.cursor() as cur:
                cur.execute("SELECT COALESCE(MAX(id), 1) FROM users")
                max_uid = cur.fetchone()[0]
        total = 0
        for _ in range(n):
            uid = rnd.randint(1, max_uid)
            if self.is_sqlite:
                total += self.conn.execute(
                    f"SELECT COUNT(*) FROM orders WHERE user_id = {ph}", (uid,)
                ).fetchone()[0]
            else:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s", (uid,))
                    total += cur.fetchone()[0]
        return total

    def complex_join(self, n: int) -> int:
        sql = """
        SELECT u.id, SUM(o.quantity * p.price_cents) AS spend
        FROM users u
        JOIN orders o ON o.user_id = u.id
        JOIN products p ON p.id = o.product_id
        GROUP BY u.id
        """
        if self.is_sqlite:
            rows = self.conn.execute(sql).fetchall()
        else:
            with self.conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return len(rows)

    def teardown(self) -> None:
        if self.conn is not None:
            self.conn.close()


def _count_lines(path: str) -> int:
    return sum(
        1 for ln in Path(path).read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    )
