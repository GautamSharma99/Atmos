"""Idempotent historical backfill of OpenAQ AQI + Open-Meteo weather."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

from airqualitycast.config import get_logger, get_settings
from airqualitycast.db.connection import get_conn
from airqualitycast.db.upsert import (
    upsert_silver_aqi,
    upsert_stations,
    upsert_weather,
)
from airqualitycast.ingestion.aqicn_client import AQICNClient
from airqualitycast.ingestion.models import (
    AQIComponents,
    StationFeed,
    StationSearchResult,
)
from airqualitycast.ingestion.openaq_client import OpenAQClient
from airqualitycast.ingestion.openmeteo_client import OpenMeteoClient

log = get_logger(__name__)

_PARAMETER_TO_FIELD = {
    "pm25": "pm25",
    "pm10": "pm10",
    "no2": "no2",
    "so2": "so2",
    "o3": "o3",
    "co": "co",
}


async def backfill(years: float = 1.0, min_stations: int = 50) -> None:
    """Run a one-time backfill of historical AQI + weather across India."""
    settings = get_settings()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=int(365 * years))

    async with OpenAQClient(api_key=settings.openaq_api_key.get_secret_value()) as oaq:
        locations = await oaq.list_locations_in_india(limit=max(min_stations, 200))
        log.info("backfill.locations", n=len(locations))

        # Register OpenAQ locations as stations.
        with get_conn() as conn:
            search_records = [
                StationSearchResult(
                    uid=str(loc.id),
                    station_name=loc.name,
                    latitude=loc.latitude,
                    longitude=loc.longitude,
                    country=loc.country,
                )
                for loc in locations
            ]
            upsert_stations(conn, search_records, source="openaq")

        # Walk locations, pull measurements, group by hour, upsert silver.
        for loc in locations[:max(min_stations, 50)]:
            try:
                meas = await oaq.get_measurements(loc.id, start, end)
            except Exception as exc:
                log.warning("backfill.openaq_failed", loc_id=loc.id, error=str(exc))
                continue

            if not meas:
                continue

            # Bucket measurements by (hour, parameter).
            bucket: dict[datetime, dict[str, float]] = {}
            for m in meas:
                ts = m.measured_at.replace(minute=0, second=0, microsecond=0)
                field = _PARAMETER_TO_FIELD.get(m.parameter)
                if field is None:
                    continue
                bucket.setdefault(ts, {})[field] = m.value

            feeds = [
                StationFeed(
                    station_uid=str(loc.id),
                    station_name=loc.name,
                    latitude=loc.latitude,
                    longitude=loc.longitude,
                    measured_at=ts,
                    components=AQIComponents(**vals),
                )
                for ts, vals in bucket.items()
            ]
            with get_conn() as conn:
                inserted = upsert_silver_aqi(conn, feeds, source="openaq")
            log.info("backfill.openaq_loc_done", loc_id=loc.id, rows=inserted)

    # Weather backfill for the same coordinates.
    await _backfill_weather(
        [(f"openaq:{loc.id}", loc.latitude, loc.longitude) for loc in locations[:min_stations]],
        start.date(),
        end.date(),
    )


async def _backfill_weather(
    stations: list[tuple[str, float, float]], start: date, end: date
) -> None:
    async with OpenMeteoClient() as om:
        for station_id, lat, lon in stations:
            try:
                readings = await om.get_historical_weather(lat, lon, start, end)
            except Exception as exc:
                log.warning("backfill.weather_failed", station_id=station_id, error=str(exc))
                continue
            if not readings:
                continue
            with get_conn() as conn:
                inserted = upsert_weather(conn, station_id, readings)
            log.info("backfill.weather_done", station_id=station_id, rows=inserted)


async def bootstrap_aqicn_stations(keywords: list[str] | None = None) -> int:
    """Discover AQICN stations across major Indian cities."""
    keywords = keywords or [
        "Delhi", "Mumbai", "Kolkata", "Chennai", "Bengaluru", "Hyderabad",
        "Ahmedabad", "Pune", "Jaipur", "Lucknow", "Kanpur", "Nagpur",
        "Patna", "Indore", "Bhopal", "Ludhiana", "Agra", "Varanasi",
        "Amritsar", "Chandigarh", "Gurugram", "Noida", "Faridabad", "Ghaziabad",
        "Surat", "Vadodara", "Visakhapatnam", "Coimbatore", "Kochi",
        "Thiruvananthapuram", "Bhubaneswar", "Ranchi", "Dehradun", "Shimla",
        "Srinagar", "Guwahati", "Mysuru", "Mangaluru", "Madurai", "Tiruchirappalli",
    ]
    settings = get_settings()
    seen: dict[str, StationSearchResult] = {}

    async with AQICNClient(token=settings.aqicn_token.get_secret_value()) as client:
        for kw in keywords:
            results = await client.search_stations_by_keyword(kw)
            for r in results:
                if r.country and r.country.upper() not in {"IN", "INDIA"}:
                    continue
                seen.setdefault(r.uid, r)
            await asyncio.sleep(0.2)

    if not seen:
        log.warning("bootstrap.no_stations_found")
        return 0

    with get_conn() as conn:
        n = upsert_stations(conn, seen.values(), source="aqicn")
    log.info("bootstrap.stations_upserted", n=n)
    return n
