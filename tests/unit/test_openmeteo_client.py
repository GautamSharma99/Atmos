"""Unit tests for Open-Meteo client parsing."""
from __future__ import annotations

import httpx
import pytest
import respx

from airqualitycast.ingestion.openmeteo_client import OpenMeteoClient, _parse_hourly


def test_parse_hourly_handles_nulls(openmeteo_payload: dict) -> None:
    rows = _parse_hourly(openmeteo_payload, is_forecast=True)
    assert len(rows) == 3
    assert rows[0].temperature_2m == pytest.approx(18.4)
    assert rows[2].boundary_layer_height is None
    assert all(r.is_forecast for r in rows)
    assert all(r.measured_at.utcoffset().total_seconds() == 0 for r in rows)


def test_parse_hourly_empty() -> None:
    assert _parse_hourly({}, is_forecast=True) == []


@pytest.mark.asyncio
async def test_get_current_weather(openmeteo_payload: dict) -> None:
    async with OpenMeteoClient() as om:
        with respx.mock(assert_all_called=False) as rx:
            rx.get("https://api.open-meteo.com/v1/forecast").mock(
                return_value=httpx.Response(200, json=openmeteo_payload)
            )
            readings = await om.get_current_weather(28.6, 77.2)
    assert len(readings) == 3
    assert readings[0].latitude == pytest.approx(28.6)
