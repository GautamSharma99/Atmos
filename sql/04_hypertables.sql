-- Convert time-series tables into TimescaleDB hypertables.
SELECT create_hypertable('bronze.aqi_readings_raw', 'ingested_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE);

SELECT create_hypertable('silver.aqi_readings', 'measured_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

SELECT create_hypertable('silver.weather', 'measured_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

-- Retention: drop bronze raw payloads after 30 days.
SELECT add_retention_policy('bronze.aqi_readings_raw', INTERVAL '30 days', if_not_exists => TRUE);

-- Compression for chunks > 14 days old on silver time-series.
ALTER TABLE silver.aqi_readings SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'station_id'
);
ALTER TABLE silver.weather SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'station_id'
);

SELECT add_compression_policy('silver.aqi_readings', INTERVAL '14 days', if_not_exists => TRUE);
SELECT add_compression_policy('silver.weather', INTERVAL '14 days', if_not_exists => TRUE);
