-- =====================================================================
-- silver.stations  (canonical station registry)
-- =====================================================================
CREATE TABLE IF NOT EXISTS silver.stations (
    station_id        TEXT PRIMARY KEY,
    station_name      TEXT NOT NULL,
    city              TEXT,
    state             TEXT,
    country           TEXT NOT NULL DEFAULT 'IN',
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    source            TEXT NOT NULL,
    source_station_id TEXT NOT NULL,
    active            BOOLEAN NOT NULL DEFAULT true,
    geom              GEOGRAPHY(POINT, 4326),
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at      TIMESTAMPTZ
);

-- Auto-populate geom from lat/lon.
CREATE OR REPLACE FUNCTION silver.set_station_geom()
RETURNS TRIGGER AS $$
BEGIN
    NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_stations_geom ON silver.stations;
CREATE TRIGGER trg_stations_geom
    BEFORE INSERT OR UPDATE OF latitude, longitude ON silver.stations
    FOR EACH ROW EXECUTE FUNCTION silver.set_station_geom();

-- =====================================================================
-- bronze.aqi_readings_raw  (append-only raw API payloads)
-- =====================================================================
CREATE TABLE IF NOT EXISTS bronze.aqi_readings_raw (
    id           BIGSERIAL,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source       TEXT NOT NULL,
    station_id   TEXT,
    http_status  INTEGER,
    payload      JSONB NOT NULL,
    PRIMARY KEY (id, ingested_at)
);

-- =====================================================================
-- silver.aqi_readings  (cleaned, typed, deduplicated)
-- =====================================================================
CREATE TABLE IF NOT EXISTS silver.aqi_readings (
    station_id          TEXT NOT NULL REFERENCES silver.stations(station_id),
    measured_at         TIMESTAMPTZ NOT NULL,
    pm25                DOUBLE PRECISION,
    pm10                DOUBLE PRECISION,
    no2                 DOUBLE PRECISION,
    so2                 DOUBLE PRECISION,
    o3                  DOUBLE PRECISION,
    co                  DOUBLE PRECISION,
    aqi                 INTEGER,
    dominant_pollutant  TEXT,
    source              TEXT NOT NULL,
    ingested_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_id, measured_at)
);

-- =====================================================================
-- silver.weather
-- =====================================================================
CREATE TABLE IF NOT EXISTS silver.weather (
    station_id              TEXT NOT NULL REFERENCES silver.stations(station_id),
    measured_at             TIMESTAMPTZ NOT NULL,
    temperature_2m          DOUBLE PRECISION,
    relative_humidity_2m    DOUBLE PRECISION,
    wind_speed_10m          DOUBLE PRECISION,
    wind_direction_10m      DOUBLE PRECISION,
    precipitation           DOUBLE PRECISION,
    surface_pressure        DOUBLE PRECISION,
    boundary_layer_height   DOUBLE PRECISION,
    is_forecast             BOOLEAN NOT NULL DEFAULT false,
    ingested_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (station_id, measured_at, is_forecast)
);

-- =====================================================================
-- silver.fires  (NASA FIRMS VIIRS detections)
-- =====================================================================
CREATE TABLE IF NOT EXISTS silver.fires (
    fire_id      TEXT PRIMARY KEY,
    detected_at  TIMESTAMPTZ NOT NULL,
    latitude     DOUBLE PRECISION NOT NULL,
    longitude    DOUBLE PRECISION NOT NULL,
    brightness   DOUBLE PRECISION,
    frp          DOUBLE PRECISION,
    confidence   TEXT,
    satellite    TEXT,
    daynight     TEXT,
    geom         GEOGRAPHY(POINT, 4326),
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION silver.set_fire_geom()
RETURNS TRIGGER AS $$
BEGIN
    NEW.geom := ST_SetSRID(ST_MakePoint(NEW.longitude, NEW.latitude), 4326)::geography;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_fires_geom ON silver.fires;
CREATE TRIGGER trg_fires_geom
    BEFORE INSERT OR UPDATE OF latitude, longitude ON silver.fires
    FOR EACH ROW EXECUTE FUNCTION silver.set_fire_geom();

-- =====================================================================
-- silver.ingestion_runs  (observability)
-- =====================================================================
CREATE TABLE IF NOT EXISTS silver.ingestion_runs (
    run_id            BIGSERIAL PRIMARY KEY,
    dag_id            TEXT NOT NULL,
    task_id           TEXT NOT NULL,
    source            TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    ended_at          TIMESTAMPTZ,
    status            TEXT NOT NULL CHECK (status IN ('success', 'failure', 'partial')),
    records_fetched   INTEGER,
    records_inserted  INTEGER,
    error_message     TEXT
);
