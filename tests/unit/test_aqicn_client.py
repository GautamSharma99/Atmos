"""Unit tests for the AQICN client and parser."""
from __future__ import annotations

import httpx
import pytest
import respx

from airqualitycast.ingestion.aqicn_client import AQICNClient, _parse_station_feed


def test_parse_station_feed_happy_path(aqicn_payload: dict) -> None:
    feed = _parse_station_feed("11277", aqicn_payload["data"])
    assert feed is not None
    assert feed.station_uid == "11277"
    assert feed.station_name.startswith("ITO")
    assert feed.aqi == 168
    assert feed.components.pm25 == pytest.approx(168.0)
    assert feed.components.pm10 == pytest.approx(92.0)
    assert feed.dominant_pollutant == "pm25"
    assert feed.measured_at.tzinfo is not None  # UTC normalised
    assert feed.measured_at.utcoffset().total_seconds() == 0


def test_parse_handles_aqi_dash() -> None:
    feed = _parse_station_feed("1", {
        "aqi": "-",
        "city": {"name": "x", "geo": [10.0, 20.0]},
        "iaqi": {},
        "time": {"iso": "2025-01-01T00:00:00+00:00"},
    })
    assert feed is not None
    assert feed.aqi is None


def test_parse_returns_none_when_no_geo() -> None:
    assert _parse_station_feed("1", {"city": {"name": "x"}, "iaqi": {}, "time": {}}) is None


@pytest.mark.asyncio
async def test_get_station_feed_returns_none_on_404(aqicn_payload: dict) -> None:
    async with AQICNClient(token="abc") as client:
        with respx.mock(assert_all_called=False) as rx:
            rx.get("https://api.waqi.info/feed/@99/").mock(
                return_value=httpx.Response(404, json={"status": "error"})
            )
            result = await client.get_station_feed("99")
    assert result is None


@pytest.mark.asyncio
async def test_get_station_feed_parses_ok_response(aqicn_payload: dict) -> None:
    async with AQICNClient(token="abc") as client:
        with respx.mock(assert_all_called=False) as rx:
            rx.get("https://api.waqi.info/feed/@11277/").mock(
                return_value=httpx.Response(200, json=aqicn_payload)
            )
            result = await client.get_station_feed("11277")
    assert result is not None
    assert result.aqi == 168


@pytest.mark.asyncio
async def test_search_returns_results() -> None:
    body = {
        "status": "ok",
        "data": [
            {
                "uid": 11277,
                "station": {"name": "ITO Delhi", "geo": [28.6, 77.2], "country": "IN"},
            }
        ],
    }
    async with AQICNClient(token="abc") as client:
        with respx.mock(assert_all_called=False) as rx:
            rx.get("https://api.waqi.info/search/").mock(
                return_value=httpx.Response(200, json=body)
            )
            results = await client.search_stations_by_keyword("delhi")
    assert len(results) == 1
    assert results[0].uid == "11277"


def test_token_required() -> None:
    with pytest.raises(ValueError):
        AQICNClient(token="")
