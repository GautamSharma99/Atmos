"""DAG-side DB helper: prefer Airflow Connection, fall back to env-driven pool."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg


@contextmanager
def airflow_conn() -> Iterator[psycopg.Connection]:
    """Yield a psycopg connection using the `timescale_default` Airflow Connection."""
    try:
        from airflow.hooks.base import BaseHook
        c = BaseHook.get_connection("timescale_default")
        dsn = (
            f"postgresql://{c.login}:{c.password}@{c.host}:{c.port or 5432}/{c.schema}"
        )
    except Exception:
        from airqualitycast.config import get_settings
        dsn = get_settings().db_dsn

    with psycopg.connect(dsn) as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
