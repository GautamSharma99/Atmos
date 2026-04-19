"""Integration tests for DB upserts. Requires TEST_DATABASE_URL pointing at TimescaleDB."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pytest

from airqualitycast.db.upsert import (
    insert_bronze_aqi,
    record_run,
    upsert_silver_aqi,
    upsert_stations,
)
from airqualitycast.ingestion.aqicn_client import _parse_station_feed

pytestmark = pytest.mark.integration

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


@pytest.fixture(scope="module")
def conn(db_url: str | None):
    if not db_url:
        pytest.skip("TEST_DATABASE_URL not set")
    with psycopg.connect(db_url) as c:
        # Bring schema up.
        for f in sorted(SQL_DIR.glob("0*.sql")):
            c.execute(f.read_text())
        c.commit()
        yield c


def test_upsert_station_and_aqi_idempotent(conn, aqicn_payload) -> None:
    feed = _parse_station_feed("11277", aqicn_payload["data"])
    assert feed is not None

    n1 = upsert_stations(conn, [feed], source="aqicn")
    n2 = upsert_stations(conn, [feed], source="aqicn")  # conflict path
    assert n1 == n2 == 1

    insert_bronze_aqi(conn, [("aqicn", "aqicn:11277", 200, aqicn_payload["data"])])
    upsert_silver_aqi(conn, [feed], source="aqicn")
    upsert_silver_aqi(conn, [feed], source="aqicn")  # conflict path

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM silver.aqi_readings WHERE station_id = 'aqicn:11277';"
        )
        assert cur.fetchone()[0] == 1


def test_record_run(conn) -> None:
    record_run(
        conn,
        dag_id="test_dag",
        task_id="t",
        source="test",
        started_at=datetime.now(tz=timezone.utc),
        ended_at=datetime.now(tz=timezone.utc),
        status="success",
        records_fetched=1,
        records_inserted=1,
    )
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM silver.ingestion_runs WHERE dag_id = 'test_dag';")
        assert cur.fetchone()[0] >= 1
