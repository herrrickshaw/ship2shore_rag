-- Ship telemetry data lake/warehouse — DuckDB, single file, no server.
-- Replaces an earlier Cassandra design: this project's other repos
-- (global-market-data, global-stock-screener, agri-commodity-tracker,
-- market-correlation-matrices) all use a plain embedded file for exactly
-- this shape of problem (accumulate readings over time, query with SQL,
-- gitignore the file, no daemon to run or resource-tune) instead of a
-- clustered database, and there's no reason for a single-vessel-simulator
-- demo on one machine to be the exception.

-- Raw sensor readings — the lake, as-received. One row per reading.
CREATE TABLE IF NOT EXISTS sensor_readings (
    vessel_id     TEXT NOT NULL,
    sensor_type   TEXT NOT NULL,  -- e.g. 'engine_rpm', 'fuel_flow_lph', 'exhaust_temp_c', 'shaft_power_kw'
    reading_time  TIMESTAMP NOT NULL,
    value         DOUBLE NOT NULL,
    unit          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sensor_readings_lookup
    ON sensor_readings (vessel_id, sensor_type, reading_time);

-- Position reports (AIS-style) — same lake, distinct shape.
CREATE TABLE IF NOT EXISTS position_reports (
    vessel_id     TEXT NOT NULL,
    reading_time  TIMESTAMP NOT NULL,
    latitude      DOUBLE NOT NULL,
    longitude     DOUBLE NOT NULL,
    speed_knots   DOUBLE NOT NULL,
    heading_deg   DOUBLE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_position_reports_lookup
    ON position_reports (vessel_id, reading_time);

-- Warehouse side — 1-minute aggregates, computed on demand from the raw
-- table via SQL (DuckDB is fast enough over this volume that a materialized
-- copy / separate stream job isn't worth the extra moving part). Query this
-- view instead of re-deriving the GROUP BY in application code.
CREATE OR REPLACE VIEW sensor_minute_aggregates AS
SELECT
    vessel_id,
    sensor_type,
    time_bucket(INTERVAL '1 minute', reading_time) AS window_start,
    AVG(value)   AS avg_value,
    MIN(value)   AS min_value,
    MAX(value)   AS max_value,
    COUNT(*)     AS sample_count
FROM sensor_readings
GROUP BY vessel_id, sensor_type, window_start
ORDER BY window_start DESC;
