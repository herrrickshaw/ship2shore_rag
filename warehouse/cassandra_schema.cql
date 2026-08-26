-- Ship telemetry data lake — wide-column storage for high-frequency sensor
-- data. Deliberately separate from the Postgres ops module: that's low-
-- frequency structured records (a vessel gets added once, a maintenance job
-- gets logged occasionally); this is potentially thousands of readings per
-- vessel per day, which is exactly the write pattern Cassandra is built for
-- and Postgres is not.

CREATE KEYSPACE IF NOT EXISTS ship_telemetry
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE ship_telemetry;

-- Raw sensor readings, partitioned by (vessel_id, day) so a day's data for
-- one vessel lives together, clustered by time descending for "latest
-- reading" queries. bucket avoids unbounded-partition growth on a busy
-- vessel/sensor combination over a long day.
CREATE TABLE IF NOT EXISTS sensor_readings (
    vessel_id      text,
    reading_date   date,
    sensor_type    text,   -- e.g. 'engine_rpm', 'fuel_flow_lph', 'exhaust_temp_c', 'shaft_power_kw'
    reading_time   timestamp,
    value          double,
    unit           text,
    PRIMARY KEY ((vessel_id, reading_date, sensor_type), reading_time)
) WITH CLUSTERING ORDER BY (reading_time DESC);

-- Position reports (AIS-style) — same partitioning logic, separate table
-- since it has a distinct shape (lat/lon/speed/heading) from a scalar sensor
-- reading.
CREATE TABLE IF NOT EXISTS position_reports (
    vessel_id      text,
    reading_date   date,
    reading_time   timestamp,
    latitude       double,
    longitude      double,
    speed_knots    double,
    heading_deg    double,
    PRIMARY KEY ((vessel_id, reading_date), reading_time)
) WITH CLUSTERING ORDER BY (reading_time DESC);

-- Flink writes its windowed aggregates here — this is the "warehouse" side:
-- pre-aggregated, fast to query, instead of scanning raw readings.
CREATE TABLE IF NOT EXISTS sensor_minute_aggregates (
    vessel_id      text,
    sensor_type    text,
    window_start   timestamp,
    avg_value      double,
    min_value      double,
    max_value      double,
    sample_count   int,
    PRIMARY KEY ((vessel_id, sensor_type), window_start)
) WITH CLUSTERING ORDER BY (window_start DESC);
