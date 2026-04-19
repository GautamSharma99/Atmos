"""Replay raw AQICN payloads from bronze and re-derive silver rows."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from psycopg import Connection

from airqualitycast.config import get_logger
from airqualitycast.db.upsert import upsert_silver_aqi
from airqualitycast.ingestion.aqicn_client import _parse_station_feed

log = get_logger(__name__)


def reparse_recent_bronze(conn: Connection, lookback_hours: int = 1) -> int:
    """Read the last `lookback_hours` of bronze AQICN payloads, parse, upsert silver."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
    sql = """
        SELECT station_id, payload
        FROM bronze.aqi_readings_raw
        WHERE source = 'aqicn' AND ingested_at > %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (cutoff,))
        rows = cur.fetchall()

    feeds = []
    for station_id, payload in rows:
        if not station_id:
            continue
        # station_id stored as 'aqicn:<uid>'; strip prefix to recover bare uid
        bare_uid = station_id.split(":", 1)[-1]
        feed = _parse_station_feed(bare_uid, payload)
        if feed is not None:
            feeds.append(feed)

    inserted = upsert_silver_aqi(conn, feeds, source="aqicn")
    log.info("bronze_to_silver.reparsed", bronze_rows=len(rows), silver_upserts=inserted)
    return inserted
