"""Open-Meteo client (no auth) — current, forecast, and historical weather."""
from __future__ import annotations

from datetime import date, datetime, timezone

import httpx
from dateutil import parser as dtparser
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from airqualitycast.config import get_logger
from airqualitycast.ingestion.models import WeatherReading

log = get_logger(__name__)

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

_HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
    "surface_pressure",
    "boundary_layer_height",
]


class OpenMeteoClient:
    def __init__(self, timeout_s: float = 15.0) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout_s,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def __aenter__(self) -> OpenMeteoClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict[str, object]) -> dict:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.get(url, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp.json()
        raise RuntimeError("unreachable")

    async def get_current_weather(self, lat: float, lon: float) -> list[WeatherReading]:
        """Fetch the next 48 hours of hourly data (current + short forecast)."""
        params: dict[str, object] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(_HOURLY_VARS),
            "timezone": "UTC",
            "forecast_days": 2,
        }
        data = await self._get(_FORECAST_URL, params)
        return _parse_hourly(data, is_forecast=True)

    async def get_historical_weather(
        self, lat: float, lon: float, start: date, end: date
    ) -> list[WeatherReading]:
        params: dict[str, object] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(_HOURLY_VARS),
            "timezone": "UTC",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        }
        data = await self._get(_ARCHIVE_URL, params)
        return _parse_hourly(data, is_forecast=False)

    async def batch_get_current(
        self, coords: list[tuple[float, float]]
    ) -> list[WeatherReading]:
        """Open-Meteo supports comma-separated lat/lon for batched requests (≤100)."""
        if not coords:
            return []
        out: list[WeatherReading] = []
        for chunk_start in range(0, len(coords), 100):
            chunk = coords[chunk_start : chunk_start + 100]
            params: dict[str, object] = {
                "latitude": ",".join(f"{lat:.4f}" for lat, _ in chunk),
                "longitude": ",".join(f"{lon:.4f}" for _, lon in chunk),
                "hourly": ",".join(_HOURLY_VARS),
                "timezone": "UTC",
                "forecast_days": 2,
            }
            data = await self._get(_FORECAST_URL, params)
            # Batched responses come back as a list of dicts (one per coord).
            if isinstance(data, list):
                for entry in data:
                    out.extend(_parse_hourly(entry, is_forecast=True))
            else:
                out.extend(_parse_hourly(data, is_forecast=True))
        return out


def _parse_hourly(data: dict, *, is_forecast: bool) -> list[WeatherReading]:
    if not data or "hourly" not in data:
        return []
    hourly = data["hourly"]
    times = hourly.get("time") or []
    lat = float(data.get("latitude", 0.0))
    lon = float(data.get("longitude", 0.0))

    out: list[WeatherReading] = []
    for i, t in enumerate(times):
        try:
            ts = dtparser.isoparse(t).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        out.append(
            WeatherReading(
                latitude=lat,
                longitude=lon,
                measured_at=ts,
                temperature_2m=_idx(hourly.get("temperature_2m"), i),
                relative_humidity_2m=_idx(hourly.get("relative_humidity_2m"), i),
                wind_speed_10m=_idx(hourly.get("wind_speed_10m"), i),
                wind_direction_10m=_idx(hourly.get("wind_direction_10m"), i),
                precipitation=_idx(hourly.get("precipitation"), i),
                surface_pressure=_idx(hourly.get("surface_pressure"), i),
                boundary_layer_height=_idx(hourly.get("boundary_layer_height"), i),
                is_forecast=is_forecast,
            )
        )
    return out


def _idx(arr: list | None, i: int) -> float | None:
    if arr is None or i >= len(arr):
        return None
    v = arr[i]
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
