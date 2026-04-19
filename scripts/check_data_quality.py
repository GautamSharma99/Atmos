"""One-shot data quality run, writes docs/data_quality_report.json."""
from __future__ import annotations

from airqualitycast.config import configure_logging, get_logger
from airqualitycast.db.connection import get_conn
from airqualitycast.quality.checks import run_all_checks
from airqualitycast.quality.reporter import write_report


def main() -> None:
    configure_logging()
    log = get_logger(__name__)
    with get_conn() as conn:
        report = run_all_checks(conn)
    out = write_report(report)
    log.info("quality.report_written", path=str(out), failed=report.failed)
    if report.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
