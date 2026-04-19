"""Idempotent batch upsert helpers for silver and bronze tables."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Json

from airqualitycast.config import get_logger
from airqualitycast.ingestion.models import (
    FireDetection,
    StationFeed,
    StationSearchResult,
    WeatherReading,
)

log = get_logger(__name__)


def upsert_stations(
    conn: Connection,
    stations: Iterable[StationSearchResult | StationFeed],
    *,
    source: str = "aqicn",
) -> int:
    rows: list[tuple[Any, ...]] = []
    for s in stations:
        if isinstance(s, StationFeed):
            uid, name, lat, lon = s.station_uid, s.station_name, s.latitude, s.longitude
        else:
            uid, name, lat, lon = s.uid, s.station_name, s.latitude, s.longitude
        station_id = f"{source}:{uid}"
        rows.append((station_id, name, lat, lon, source, uid))

    if not rows:
        return 0

    sql = """
        INSERT INTO silver.stations
            (station_id, station_name, latitude, longitude, source, source_station_id, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (station_id) DO UPDATE SET
            station_name = EXCLUDED.station_name,
            latitude     = EXCLUDED.latitude,
            longitude    = EXCLUDED.longitude,
            last_seen_at = NOW();
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def insert_bronze_aqi(
    conn: Connection,
    payloads: Iterable[tuple[str, str, int, dict]],
) -> int:
    """payloads: iterable of (source, station_id, http_status, payload_dict)."""
    rows = [
        (source, station_id, status, Json(payload))
        for source, station_id, status, payload in payloads
    ]
    if not rows:
        return 0
    sql = """
        INSERT INTO bronze.aqi_readings_raw (source, station_id, http_status, payload)
        VALUES (%s, %s, %s, %s);
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def upsert_silver_aqi(
    conn: Connection,
    feeds: Iterable[StationFeed],
    *,
    source: str = "aqicn",
) -> int:
    rows = []
    for f in feeds:
        rows.append(
            (
                f"{source}:{f.station_uid}",
                f.measured_at,
                f.components.pm25,
                f.components.pm10,
                f.components.no2,
                f.components.so2,
                f.components.o3,
                f.components.co,
                f.aqi,
                f.dominant_pollutant,
                source,
            )
        )
    if not rows:
        return 0
    sql = """
        INSERT INTO silver.aqi_readings
            (station_id, measured_at, pm25, pm10, no2, so2, o3, co,
             aqi, dominant_pollutant, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (station_id, measured_at) DO UPDATE SET
            pm25 = EXCLUDED.pm25,
            pm10 = EXCLUDED.pm10,
            no2  = EXCLUDED.no2,
            so2  = EXCLUDED.so2,
            o3   = EXCLUDED.o3,
            co   = EXCLUDED.co,
            aqi  = EXCLUDED.aqi,
            dominant_pollutant = EXCLUDED.dominant_pollutant,
            ingested_at = NOW();
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def upsert_weather(
    conn: Connection,
    station_id: str,
    readings: Iterable[WeatherReading],
) -> int:
    rows = [
        (
            station_id,
            r.measured_at,
            r.temperature_2m,
            r.relative_humidity_2m,
            r.wind_speed_10m,
            r.wind_direction_10m,
            r.precipitation,
            r.surface_pressure,
            r.boundary_layer_height,
            r.is_forecast,
        )
        for r in readings
    ]
    if not rows:
        return 0
    sql = """
        INSERT INTO silver.weather
            (station_id, measured_at, temperature_2m, relative_humidity_2m,
             wind_speed_10m, wind_direction_10m, precipitation,
             surface_pressure, boundary_layer_height, is_forecast)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (station_id, measured_at, is_forecast) DO UPDATE SET
            temperature_2m        = EXCLUDED.temperature_2m,
            relative_humidity_2m  = EXCLUDED.relative_humidity_2m,
            wind_speed_10m        = EXCLUDED.wind_speed_10m,
            wind_direction_10m    = EXCLUDED.wind_direction_10m,
            precipitation         = EXCLUDED.precipitation,
            surface_pressure      = EXCLUDED.surface_pressure,
            boundary_layer_height = EXCLUDED.boundary_layer_height,
            ingested_at           = NOW();
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def upsert_fires(conn: Connection, fires: Iterable[FireDetection]) -> int:
    rows = [
        (
            f.fire_id,
            f.detected_at,
            f.latitude,
            f.longitude,
            f.brightness,
            f.frp,
            f.confidence,
            f.satellite,
            f.daynight,
        )
        for f in fires
    ]
    if not rows:
        return 0
    sql = """
        INSERT INTO silver.fires
            (fire_id, detected_at, latitude, longitude, brightness,
             frp, confidence, satellite, daynight)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fire_id) DO NOTHING;
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def record_run(
    conn: Connection,
    *,
    dag_id: str,
    task_id: str,
    source: str,
    started_at: datetime,
    ended_at: datetime,
    status: str,
    records_fetched: int = 0,
    records_inserted: int = 0,
    error_message: str | None = None,
) -> None:
    sql = """
        INSERT INTO silver.ingestion_runs
            (dag_id, task_id, source, started_at, ended_at, status,
             records_fetched, records_inserted, error_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    with conn.cursor() as cur:
        cur.execute(
            sql,
            (
                dag_id,
                task_id,
                source,
                started_at,
                ended_at,
                status,
                records_fetched,
                records_inserted,
                error_message,
            ),
        )


__all__ = [
    "insert_bronze_aqi",
    "record_run",
    "upsert_fires",
    "upsert_silver_aqi",
    "upsert_stations",
    "upsert_weather",
]
