"""OpenAQ v3 client — used only for one-time historical backfill."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from dateutil import parser as dtparser
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from airqualitycast.config import get_logger
from airqualitycast.ingestion.models import OpenAQLocation, OpenAQMeasurement

log = get_logger(__name__)

_BASE = "https://api.openaq.org/v3"
# 60 req/min cap — keep a 25% margin (40/min ≈ 1.5s between calls).
_MIN_INTERVAL_S = 1.5
_INDIA_COUNTRY_ID = 9


class OpenAQClient:
    def __init__(self, api_key: str, timeout_s: float = 30.0) -> None:
        if not api_key:
            raise ValueError("OpenAQ api_key is required")
        self._client = httpx.AsyncClient(
            base_url=_BASE,
            timeout=timeout_s,
            headers={"X-API-Key": api_key},
        )
        self._lock = asyncio.Lock()
        self._last_call: float = 0.0

    async def __aenter__(self) -> OpenAQClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            wait = _MIN_INTERVAL_S - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = asyncio.get_event_loop().time()

    async def _get(self, path: str, params: dict[str, object]) -> dict:
        await self._throttle()
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp.json()
        raise RuntimeError("unreachable")

    async def list_locations_in_india(self, limit: int = 1000) -> list[OpenAQLocation]:
        out: list[OpenAQLocation] = []
        page = 1
        while True:
            data = await self._get(
                "/locations",
                {"countries_id": _INDIA_COUNTRY_ID, "limit": min(1000, limit), "page": page},
            )
            results = data.get("results") or []
            for r in results:
                coords = r.get("coordinates") or {}
                if coords.get("latitude") is None:
                    continue
                out.append(
                    OpenAQLocation(
                        id=int(r["id"]),
                        name=r.get("name") or f"openaq_{r['id']}",
                        latitude=float(coords["latitude"]),
                        longitude=float(coords["longitude"]),
                        country=(r.get("country") or {}).get("code"),
                        city=r.get("locality"),
                    )
                )
            if len(results) < 1000 or len(out) >= limit:
                break
            page += 1
        return out[:limit]

    async def get_measurements(
        self, location_id: int, date_from: datetime, date_to: datetime
    ) -> list[OpenAQMeasurement]:
        out: list[OpenAQMeasurement] = []
        page = 1
        while True:
            data = await self._get(
                f"/locations/{location_id}/measurements",
                {
                    "date_from": date_from.astimezone(timezone.utc).isoformat(),
                    "date_to": date_to.astimezone(timezone.utc).isoformat(),
                    "limit": 1000,
                    "page": page,
                },
            )
            results = data.get("results") or []
            for r in results:
                period = (r.get("period") or {}).get("datetimeFrom") or {}
                iso = period.get("utc")
                if not iso:
                    continue
                try:
                    ts = dtparser.isoparse(iso).astimezone(timezone.utc)
                except (ValueError, TypeError):
                    continue
                out.append(
                    OpenAQMeasurement(
                        location_id=location_id,
                        parameter=(r.get("parameter") or {}).get("name", "unknown"),
                        value=float(r.get("value", 0.0)),
                        unit=(r.get("parameter") or {}).get("units", ""),
                        measured_at=ts,
                    )
                )
            if len(results) < 1000:
                break
            page += 1
        return out
