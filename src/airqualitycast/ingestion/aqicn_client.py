"""AQICN (waqi.info) async client — primary live-AQI source."""
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
from airqualitycast.ingestion.models import (
    AQIComponents,
    StationFeed,
    StationSearchResult,
)

log = get_logger(__name__)

_BASE_URL = "https://api.waqi.info"


class AQICNClient:
    """Async client for the AQICN/waqi.info v2 feed API."""

    def __init__(self, token: str, timeout_s: float = 10.0) -> None:
        if not token:
            raise ValueError("AQICN token is required")
        self._token = token
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            timeout=timeout_s,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def __aenter__(self) -> AQICNClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        params = {**(params or {}), "token": self._token}
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.get(path, params=params)
                if resp.status_code == 429 or resp.status_code >= 500:
                    resp.raise_for_status()
                return resp
        raise RuntimeError("unreachable")

    async def get_station_feed(self, station_uid: str) -> StationFeed | None:
        """Fetch a single station's current reading. Returns None on 4xx or offline."""
        try:
            resp = await self._get(f"/feed/@{station_uid}/")
        except httpx.HTTPStatusError as exc:
            log.warning("aqicn.http_error", uid=station_uid, status=exc.response.status_code)
            return None
        except httpx.HTTPError as exc:
            log.error("aqicn.transport_error", uid=station_uid, error=str(exc))
            return None

        body = resp.json()
        if body.get("status") != "ok":
            log.info("aqicn.station_offline", uid=station_uid, body_status=body.get("status"))
            return None

        data = body.get("data") or {}
        return _parse_station_feed(station_uid, data)

    async def search_stations_by_keyword(self, keyword: str) -> list[StationSearchResult]:
        try:
            resp = await self._get("/search/", {"keyword": keyword})
        except httpx.HTTPError:
            return []
        body = resp.json()
        if body.get("status") != "ok":
            return []
        out: list[StationSearchResult] = []
        for item in body.get("data") or []:
            station = item.get("station") or {}
            geo = station.get("geo") or [None, None]
            if not item.get("uid") or geo[0] is None:
                continue
            out.append(
                StationSearchResult(
                    uid=str(item["uid"]),
                    station_name=station.get("name", ""),
                    latitude=float(geo[0]),
                    longitude=float(geo[1]),
                    country=station.get("country"),
                )
            )
        return out

    async def batch_get_station_feeds(
        self, station_uids: list[str], concurrency: int = 5
    ) -> list[StationFeed]:
        sem = asyncio.Semaphore(concurrency)

        async def _one(uid: str) -> StationFeed | None:
            async with sem:
                return await self.get_station_feed(uid)

        results = await asyncio.gather(*(_one(uid) for uid in station_uids))
        return [r for r in results if r is not None]


def _parse_station_feed(station_uid: str, data: dict) -> StationFeed | None:
    """Normalise raw AQICN payload into a typed StationFeed."""
    aqi_raw = data.get("aqi")
    aqi: int | None
    if aqi_raw in (None, "-", ""):
        aqi = None
    else:
        try:
            aqi = int(aqi_raw)
        except (TypeError, ValueError):
            aqi = None

    iaqi = data.get("iaqi") or {}

    def _v(key: str) -> float | None:
        node = iaqi.get(key)
        if isinstance(node, dict) and "v" in node:
            try:
                return float(node["v"])
            except (TypeError, ValueError):
                return None
        return None

    components = AQIComponents(
        pm25=_v("pm25"),
        pm10=_v("pm10"),
        no2=_v("no2"),
        so2=_v("so2"),
        o3=_v("o3"),
        co=_v("co"),
    )

    time_node = data.get("time") or {}
    iso = time_node.get("iso") or time_node.get("s")
    if iso:
        try:
            measured_at = dtparser.isoparse(iso).astimezone(timezone.utc)
        except (ValueError, TypeError):
            measured_at = datetime.now(tz=timezone.utc)
    else:
        measured_at = datetime.now(tz=timezone.utc)

    city = data.get("city") or {}
    geo = city.get("geo") or [None, None]
    if geo[0] is None:
        return None

    return StationFeed(
        station_uid=str(data.get("idx") or station_uid),
        station_name=city.get("name", ""),
        latitude=float(geo[0]),
        longitude=float(geo[1]),
        aqi=aqi,
        dominant_pollutant=data.get("dominentpol"),
        measured_at=measured_at,
        components=components,
        raw_payload=data,
    )
