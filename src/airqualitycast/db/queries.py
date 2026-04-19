"""Read-side helpers used by DAGs and quality checks."""
from __future__ import annotations

from typing import Any

from psycopg import Connection


def get_active_stations(conn: Connection, source: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT station_id, source_station_id, station_name, latitude, longitude, source
        FROM silver.stations
        WHERE active = true
    """
    params: tuple[Any, ...] = ()
    if source:
        sql += " AND source = %s"
        params = (source,)
    sql += " ORDER BY station_id;"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description or []]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def deactivate_stale_stations(conn: Connection, hours: int = 24) -> int:
    """Mark stations with no data > N hours as inactive."""
    sql = f"""
        UPDATE silver.stations s
        SET active = false
        WHERE active = true
          AND NOT EXISTS (
              SELECT 1 FROM silver.aqi_readings r
              WHERE r.station_id = s.station_id
                AND r.measured_at > NOW() - INTERVAL '{int(hours)} hours'
          );
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.rowcount or 0


def pm25_missing_rate_per_station(conn: Connection, days: int = 7) -> list[dict[str, Any]]:
    sql = f"""
        WITH expected AS (
            SELECT s.station_id, {int(days)} * 24 AS expected_n
            FROM silver.stations s WHERE s.active = true
        ),
        observed AS (
            SELECT station_id, COUNT(*) FILTER (WHERE pm25 IS NOT NULL) AS got
            FROM silver.aqi_readings
            WHERE measured_at > NOW() - INTERVAL '{int(days)} days'
            GROUP BY station_id
        )
        SELECT e.station_id,
               COALESCE(o.got, 0) AS observed,
               e.expected_n        AS expected,
               CASE WHEN e.expected_n = 0 THEN 1.0
                    ELSE 1.0 - LEAST(1.0, COALESCE(o.got, 0)::float / e.expected_n)
               END AS missing_rate
        FROM expected e
        LEFT JOIN observed o USING (station_id)
        ORDER BY missing_rate DESC;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description or []]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def duplicate_row_count(conn: Connection) -> int:
    sql = """
        SELECT COUNT(*) FROM (
            SELECT station_id, measured_at, COUNT(*) c
            FROM silver.aqi_readings
            GROUP BY station_id, measured_at
            HAVING COUNT(*) > 1
        ) t;
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return int(row[0]) if row else 0


def global_pm25_null_rate(conn: Connection, days: int = 7) -> float:
    sql = f"""
        SELECT
            CASE WHEN COUNT(*) = 0 THEN 0
                 ELSE COUNT(*) FILTER (WHERE pm25 IS NULL)::float / COUNT(*)
            END AS null_rate
        FROM silver.aqi_readings
        WHERE measured_at > NOW() - INTERVAL '{int(days)} days';
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
        return float(row[0]) if row else 0.0
