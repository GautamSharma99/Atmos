"""Hourly Open-Meteo weather ingestion (offset 15 min from AQI)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pendulum
from airflow.decorators import dag, task

from airqualitycast.config import configure_logging, get_logger
from airqualitycast.db.upsert import record_run, upsert_weather
from airqualitycast.ingestion.openmeteo_client import OpenMeteoClient
from utils.alerting import on_failure_callback
from utils.db import airflow_conn

configure_logging()
log = get_logger(__name__)
DAG_ID = "ingest_weather_hourly"


@dag(
    dag_id=DAG_ID,
    schedule="15 * * * *",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "on_failure_callback": on_failure_callback,
    },
    tags=["weather", "ingest"],
)
def ingest_weather_hourly() -> None:
    @task
    def get_active_stations() -> list[dict]:
        with airflow_conn() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT station_id, latitude, longitude FROM silver.stations WHERE active = true;"
            )
            return [
                {"station_id": r[0], "lat": float(r[1]), "lon": float(r[2])}
                for r in cur.fetchall()
            ]

    @task
    def fetch_and_upsert(stations: list[dict]) -> dict:
        started = datetime.now(tz=timezone.utc)
        if not stations:
            return {"fetched": 0, "inserted": 0, "started": started.isoformat()}

        async def run() -> dict[str, list]:
            results: dict[str, list] = {}
            async with OpenMeteoClient() as om:
                # Open-Meteo's batched response order matches input order.
                for chunk_start in range(0, len(stations), 100):
                    chunk = stations[chunk_start : chunk_start + 100]
                    coords = [(s["lat"], s["lon"]) for s in chunk]
                    readings = await om.batch_get_current(coords)
                    # Map by (lat, lon) to redistribute back to station_id.
                    by_coord: dict[tuple[float, float], list] = {}
                    for r in readings:
                        by_coord.setdefault(
                            (round(r.latitude, 2), round(r.longitude, 2)), []
                        ).append(r)
                    for s in chunk:
                        key = (round(s["lat"], 2), round(s["lon"], 2))
                        results[s["station_id"]] = by_coord.get(key, [])
            return results

        per_station = asyncio.run(run())

        total_fetched = sum(len(v) for v in per_station.values())
        total_inserted = 0
        with airflow_conn() as conn:
            for station_id, readings in per_station.items():
                total_inserted += upsert_weather(conn, station_id, readings)

        result = {
            "fetched": total_fetched,
            "inserted": total_inserted,
            "started": started.isoformat(),
        }
        log.info("weather.ingest_done", **result)
        return result

    @task(trigger_rule="all_done")
    def write_run_record(result: dict) -> None:
        with airflow_conn() as conn:
            record_run(
                conn,
                dag_id=DAG_ID,
                task_id="fetch_and_upsert",
                source="open-meteo",
                started_at=datetime.fromisoformat(result["started"]),
                ended_at=datetime.now(tz=timezone.utc),
                status="success" if result["fetched"] > 0 else "partial",
                records_fetched=result["fetched"],
                records_inserted=result["inserted"],
            )

    stations = get_active_stations()
    result = fetch_and_upsert(stations)
    write_run_record(result)


ingest_weather_hourly()
