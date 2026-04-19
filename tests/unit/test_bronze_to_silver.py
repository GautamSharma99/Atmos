"""Tests for bronze→silver re-parsing logic (no DB)."""
from __future__ import annotations

from airqualitycast.ingestion.aqicn_client import _parse_station_feed


def test_reparse_payload_idempotent(aqicn_payload: dict) -> None:
    """Parsing the same payload twice must yield equal silver rows."""
    a = _parse_station_feed("11277", aqicn_payload["data"])
    b = _parse_station_feed("11277", aqicn_payload["data"])
    assert a is not None and b is not None
    assert a.station_uid == b.station_uid
    assert a.measured_at == b.measured_at
    assert a.aqi == b.aqi
    assert a.components.pm25 == b.components.pm25
