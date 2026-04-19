"""Hourly AQICN ingestion DAG."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pendulum
from airflow.decorators import dag, task
from airflow.models import Variable

from airqualitycast.config import configure_logging, get_logger
from airqualitycast.db.upsert import (
    insert_bronze_aqi,
    record_run,
    upsert_silver_aqi,
)
from airqualitycast.ingestion.aqicn_client import AQICNClient
from utils.alerting import on_failure_callback
from utils.db import airflow_conn

configure_logging()
log = get_logger(__name__)

DAG_ID = "ingest_aqi_hourly"


@dag(
    dag_id=DAG_ID,
    schedule="0 * * * *",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "on_failure_callback": on_failure_callback,
    },
    tags=["aqi", "ingest"],
)
def ingest_aqi_hourly() -> None:
    @task(pool="aqicn_pool")
    def get_active_stations() -> list[dict]:
        with airflow_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT station_id, source_station_id "
                "FROM silver.stations WHERE source = 'aqicn' AND active = true;"
            )
            return [{"station_id": r[0], "source_uid": r[1]} for r in cur.fetchall()]

    @task(pool="aqicn_pool")
    def fetch_and_store_all(stations: list[dict]) -> dict:
        started = datetime.now(tz=timezone.utc)
        token = Variable.get("AQICN_TOKEN", default_var="")
        if not stations or not token:
            return {"fetched": 0, "inserted": 0, "started": started.isoformat(), "n_stations": 0}

        async def run() -> tuple[list, list]:
            async with AQICNClient(token=token) as client:
                feeds = await client.batch_get_station_feeds(
                    [s["source_uid"] for s in stations], concurrency=5
                )
            return feeds, stations

        feeds, _ = asyncio.run(run())

        bronze_payloads = [
            ("aqicn", f"aqicn:{f.station_uid}", 200, f.raw_payload) for f in feeds
        ]
        with airflow_conn() as conn:
            inserted_bronze = insert_bronze_aqi(conn, bronze_payloads)
            inserted_silver = upsert_silver_aqi(conn, feeds, source="aqicn")

        result = {
            "fetched": len(feeds),
            "inserted": inserted_silver,
            "bronze_rows": inserted_bronze,
            "started": started.isoformat(),
            "n_stations": len(stations),
        }
        log.info("aqi.ingest_done", **result)
        return result

    @task(trigger_rule="all_done")
    def write_run_record(stations: list[dict], result: dict) -> None:
        n_stations = result.get("n_stations") or len(stations)
        fetched = result.get("fetched", 0)
        if n_stations == 0:
            status = "failure"
        elif fetched < 0.5 * n_stations:
            status = "partial"
        else:
            status = "success"

        with airflow_conn() as conn:
            record_run(
                conn,
                dag_id=DAG_ID,
                task_id="fetch_and_store_all",
                source="aqicn",
                started_at=datetime.fromisoformat(result["started"]),
                ended_at=datetime.now(tz=timezone.utc),
                status=status,
                records_fetched=fetched,
                records_inserted=result.get("inserted", 0),
            )

    stations = get_active_stations()
    result = fetch_and_store_all(stations)
    write_run_record(stations, result)


ingest_aqi_hourly()
