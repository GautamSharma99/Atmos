-- Hourly per-city AQI rollup. Demonstrates TimescaleDB continuous aggregates.
CREATE MATERIALIZED VIEW IF NOT EXISTS gold.aqi_hourly_by_city
WITH (timescaledb.continuous) AS
SELECT
    s.city,
    time_bucket('1 hour', ar.measured_at) AS hour,
    AVG(ar.pm25) AS avg_pm25,
    AVG(ar.pm10) AS avg_pm10,
    MAX(ar.aqi)  AS max_aqi,
    COUNT(*)     AS n_readings
FROM silver.aqi_readings ar
JOIN silver.stations s ON ar.station_id = s.station_id
GROUP BY s.city, hour
WITH NO DATA;

SELECT add_continuous_aggregate_policy('gold.aqi_hourly_by_city',
    start_offset => INTERVAL '7 days',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE);
