"""Four implementations of the same four-op contract."""

from orm_bench.impls.peewee_orm import PeeweeImpl
from orm_bench.impls.psycopg_raw import RawSqlImpl
from orm_bench.impls.sa_core import SaCoreImpl
from orm_bench.impls.sa_orm import SaOrmImpl


IMPLS = [SaOrmImpl(), SaCoreImpl(), PeeweeImpl(), RawSqlImpl()]


__all__ = ["IMPLS", "PeeweeImpl", "RawSqlImpl", "SaCoreImpl", "SaOrmImpl"]
