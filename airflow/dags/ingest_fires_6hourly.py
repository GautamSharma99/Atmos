"""6-hourly NASA FIRMS VIIRS active-fire ingestion."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pendulum
from airflow.decorators import dag, task
from airflow.models import Variable

from airqualitycast.config import configure_logging, get_logger
from airqualitycast.db.upsert import record_run, upsert_fires
from airqualitycast.ingestion.firms_client import FIRMSClient
from airqualitycast.ingestion.models import FireDetection
from utils.alerting import on_failure_callback
from utils.db import airflow_conn

configure_logging()
log = get_logger(__name__)
DAG_ID = "ingest_fires_6hourly"


@dag(
    dag_id=DAG_ID,
    schedule="0 */6 * * *",
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "on_failure_callback": on_failure_callback,
    },
    tags=["fires", "ingest"],
)
def ingest_fires_6hourly() -> None:
    @task
    def fetch_and_upsert() -> dict:
        started = datetime.now(tz=timezone.utc)
        map_key = Variable.get("FIRMS_MAP_KEY", default_var="")
        if not map_key:
            log.warning("firms.no_map_key_configured")
            return {"fetched": 0, "inserted": 0, "started": started.isoformat()}

        client = FIRMSClient(map_key=map_key)
        df = client.fetch_fires_for_india(days=1)
        if df.empty:
            return {"fetched": 0, "inserted": 0, "started": started.isoformat()}

        fires = [
            FireDetection(
                fire_id=row["fire_id"],
                detected_at=row["detected_at"].to_pydatetime(),
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                brightness=row.get("brightness"),
                frp=row.get("frp"),
                confidence=row.get("confidence"),
                satellite=row.get("satellite"),
                daynight=row.get("daynight"),
            )
            for _, row in df.iterrows()
            if row["detected_at"] is not None
        ]

        with airflow_conn() as conn:
            inserted = upsert_fires(conn, fires)

        result = {
            "fetched": len(fires),
            "inserted": inserted,
            "started": started.isoformat(),
        }
        log.info("fires.ingest_done", **result)
        return result

    @task(trigger_rule="all_done")
    def write_run_record(result: dict) -> None:
        with airflow_conn() as conn:
            record_run(
                conn,
                dag_id=DAG_ID,
                task_id="fetch_and_upsert",
                source="nasa-firms",
                started_at=datetime.fromisoformat(result["started"]),
                ended_at=datetime.now(tz=timezone.utc),
                status="success" if result["fetched"] > 0 else "partial",
                records_fetched=result["fetched"],
                records_inserted=result["inserted"],
            )

    write_run_record(fetch_and_upsert())


ingest_fires_6hourly()
