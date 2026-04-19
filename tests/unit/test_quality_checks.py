"""Unit tests for the QualityReport dataclass and validators."""
from __future__ import annotations

from airqualitycast.processing.validators import clip
from airqualitycast.quality.checks import (
    PM25_MISSING_RATE_TARGET,
    QualityReport,
)


def test_clip_drops_out_of_range() -> None:
    assert clip("pm25", -5.0) is None
    assert clip("pm25", 99999.0) is None
    assert clip("pm25", 42.0) == 42.0
    assert clip("pm25", None) is None
    assert clip("unknown_field", 12345.0) == 12345.0


def test_quality_report_to_dict_counts_above_target() -> None:
    report = QualityReport(
        deactivated_stations=2,
        global_pm25_null_rate=0.10,
        duplicate_rows=0,
        per_station_missing=[
            {"station_id": "a", "missing_rate": PM25_MISSING_RATE_TARGET + 0.1},
            {"station_id": "b", "missing_rate": 0.0},
        ],
    )
    d = report.to_dict()
    assert d["stations_above_target_missing"] == 1
    assert d["n_stations_checked"] == 2
    assert d["failed"] is False
