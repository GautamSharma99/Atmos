"""Unit tests for FIRMS CSV normalisation."""
from __future__ import annotations

from io import StringIO

import pandas as pd

from airqualitycast.ingestion.firms_client import FIRMSClient, _normalize_firms


def test_normalize_constructs_fire_id(firms_csv_text: str) -> None:
    df = pd.read_csv(StringIO(firms_csv_text))
    df.columns = [c.strip().lower() for c in df.columns]
    out = _normalize_firms(df)

    assert "fire_id" in out.columns
    assert "detected_at" in out.columns
    assert "brightness" in out.columns  # bright_ti4 → brightness
    assert out["fire_id"].is_unique
    assert out["detected_at"].notna().all()
    assert str(out["detected_at"].dt.tz) == "UTC"


def test_map_key_required() -> None:
    import pytest
    with pytest.raises(ValueError):
        FIRMSClient(map_key="")
