"""Daily data quality monitoring DAG."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

from airqualitycast.config import configure_logging, get_logger
from airqualitycast.db.upsert import record_run
from airqualitycast.quality.checks import (
    PM25_NULL_RATE_FAIL_THRESHOLD,
    run_all_checks,
)
from airqualitycast.quality.reporter import write_report
from utils.alerting import on_failure_callback
from utils.db import airflow_conn

configure_logging()
log = get_logger(__name__)
DAG_ID = "data_quality_daily"


@dag(
    dag_id=DAG_ID,
    schedule="30 2 * * *",  # ≈ 08:00 IST
    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
        "on_failure_callback": on_failure_callback,
    },
    tags=["quality"],
)
def data_quality_daily() -> None:
    @task
    def run_checks() -> dict:
        started = datetime.now(tz=timezone.utc)
        with airflow_conn() as conn:
            report = run_all_checks(conn)
        out = write_report(report, Path("/opt/airquality/docs/data_quality_report.json"))
        log.info("quality.report_written", path=str(out))
        return {**report.to_dict(), "started": started.isoformat()}

    @task(trigger_rule="all_done")
    def write_run_record(result: dict) -> None:
        with airflow_conn() as conn:
            record_run(
                conn,
                dag_id=DAG_ID,
                task_id="run_checks",
                source="quality",
                started_at=datetime.fromisoformat(result["started"]),
                ended_at=datetime.now(tz=timezone.utc),
                status="failure" if result.get("failed") else "success",
                records_fetched=result.get("n_stations_checked", 0),
                records_inserted=0,
                error_message=result.get("failure_reason"),
            )

    @task
    def fail_if_unhealthy(result: dict) -> None:
        if result.get("failed"):
            raise RuntimeError(
                f"Data quality FAILED: PM2.5 null rate "
                f"{result.get('global_pm25_null_rate', 0):.1%} > "
                f"{PM25_NULL_RATE_FAIL_THRESHOLD:.0%}"
            )

    result = run_checks()
    write_run_record(result)
    fail_if_unhealthy(result)


data_quality_daily()
