"""Data quality checks invoked by the daily DQ DAG."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from psycopg import Connection

from airqualitycast.config import get_logger
from airqualitycast.db.queries import (
    deactivate_stale_stations,
    duplicate_row_count,
    global_pm25_null_rate,
    pm25_missing_rate_per_station,
)

log = get_logger(__name__)

PM25_NULL_RATE_FAIL_THRESHOLD = 0.30
PM25_MISSING_RATE_TARGET = 0.15


@dataclass
class QualityReport:
    deactivated_stations: int = 0
    global_pm25_null_rate: float = 0.0
    duplicate_rows: int = 0
    per_station_missing: list[dict[str, Any]] = field(default_factory=list)
    failed: bool = False
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "deactivated_stations": self.deactivated_stations,
            "global_pm25_null_rate": round(self.global_pm25_null_rate, 4),
            "duplicate_rows": self.duplicate_rows,
            "stations_above_target_missing": sum(
                1 for r in self.per_station_missing
                if r["missing_rate"] > PM25_MISSING_RATE_TARGET
            ),
            "n_stations_checked": len(self.per_station_missing),
            "failed": self.failed,
            "failure_reason": self.failure_reason,
        }


def run_all_checks(conn: Connection) -> QualityReport:
    report = QualityReport()
    report.deactivated_stations = deactivate_stale_stations(conn, hours=24)
    report.per_station_missing = pm25_missing_rate_per_station(conn, days=7)
    report.duplicate_rows = duplicate_row_count(conn)
    report.global_pm25_null_rate = global_pm25_null_rate(conn, days=7)

    if report.global_pm25_null_rate > PM25_NULL_RATE_FAIL_THRESHOLD:
        report.failed = True
        report.failure_reason = (
            f"Global PM2.5 null rate {report.global_pm25_null_rate:.1%} exceeds "
            f"{PM25_NULL_RATE_FAIL_THRESHOLD:.0%} threshold."
        )

    log.info("quality.report", **report.to_dict())
    return report
