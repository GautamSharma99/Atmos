# Database Schema

Three medallion schemas: `bronze` (raw), `silver` (cleaned, ML-ready), `gold` (aggregates / Phase 2 features).

## silver.stations
| column            | type                  | notes                                  |
| ----------------- | --------------------- | -------------------------------------- |
| station_id        | TEXT PK               | canonical: `<source>:<source_uid>`     |
| station_name      | TEXT                  |                                        |
| city, state       | TEXT                  | nullable                               |
| country           | TEXT, default 'IN'    |                                        |
| latitude, longitude | DOUBLE PRECISION    |                                        |
| source            | TEXT                  | aqicn / openaq / cpcb                  |
| source_station_id | TEXT                  |                                        |
| active            | BOOLEAN, default TRUE |                                        |
| geom              | GEOGRAPHY(POINT,4326) | auto-set via trigger                   |
| first_seen_at, last_seen_at | TIMESTAMPTZ |                                        |

## bronze.aqi_readings_raw  (hypertable on `ingested_at`, 1-day chunks, 30-day TTL)
| column       | type        |
| ------------ | ----------- |
| id           | BIGSERIAL   |
| ingested_at  | TIMESTAMPTZ |
| source       | TEXT        |
| station_id   | TEXT        |
| http_status  | INTEGER     |
| payload      | JSONB       |

## silver.aqi_readings  (hypertable on `measured_at`, 7-day chunks, compressed > 14 d)
PK: `(station_id, measured_at)`. Pollutant columns: `pm25, pm10, no2, so2, o3, co, aqi, dominant_pollutant, source, ingested_at`.

## silver.weather  (hypertable on `measured_at`, 7-day chunks, compressed > 14 d)
PK: `(station_id, measured_at, is_forecast)`. Variables: `temperature_2m, relative_humidity_2m, wind_speed_10m, wind_direction_10m, precipitation, surface_pressure, boundary_layer_height`.

## silver.fires
PK: `fire_id` (deterministic: `{satellite}_{date}_{time}_{lat}_{lon}`). GIST index on `geom`.

## silver.ingestion_runs
Observability: `dag_id, task_id, source, started_at, ended_at, status, records_fetched, records_inserted, error_message`.

## gold.aqi_hourly_by_city
Continuous aggregate refreshed hourly: per-city `avg_pm25`, `max_aqi`, `n_readings`.
