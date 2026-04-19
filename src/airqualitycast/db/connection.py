"""TimescaleDB connection management via psycopg3 connection pool."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg_pool import ConnectionPool

from airqualitycast.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.db_dsn,
            min_size=1,
            max_size=10,
            kwargs={"autocommit": False},
        )
    return _pool


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Yield a connection from the pool. Commits on success, rolls back on error."""
    pool = get_pool()
    with pool.connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
