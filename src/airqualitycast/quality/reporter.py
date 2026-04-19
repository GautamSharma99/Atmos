"""Persist data quality reports to JSON for the README/docs to consume."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from airqualitycast.quality.checks import QualityReport

DEFAULT_REPORT_PATH = Path("docs") / "data_quality_report.json"


def write_report(report: QualityReport, path: Path = DEFAULT_REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        **report.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path
