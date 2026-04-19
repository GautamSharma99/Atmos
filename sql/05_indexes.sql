-- silver.stations
CREATE INDEX IF NOT EXISTS idx_stations_geom ON silver.stations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_stations_source_active ON silver.stations (source, active);

-- silver.aqi_readings
CREATE INDEX IF NOT EXISTS idx_aqi_station_time ON silver.aqi_readings (station_id, measured_at DESC);

-- silver.weather
CREATE INDEX IF NOT EXISTS idx_weather_station_time ON silver.weather (station_id, measured_at DESC);

-- silver.fires
CREATE INDEX IF NOT EXISTS idx_fires_geom ON silver.fires USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_fires_detected ON silver.fires (detected_at DESC);

-- silver.ingestion_runs
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_dag_time
    ON silver.ingestion_runs (dag_id, started_at DESC);
