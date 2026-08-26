"""PyFlink job: Kafka (sensor readings + position reports) -> Cassandra, two
ways at once via a single StatementSet (one Kafka read per source topic,
fanned out to three sinks in one Flink job — not three separate jobs each
re-reading the topic):

  1. Raw passthrough into sensor_readings / position_reports — the "lake"
     side: every reading, unaggregated, exactly as received.
  2. 1-minute tumbling-window aggregation into sensor_minute_aggregates —
     the "warehouse" side: pre-aggregated, fast to query.

Requires the Flink Kafka and Cassandra SQL connector JARs on the classpath —
see warehouse/README.md for exact versions and where to put them (jars/,
mounted into the Flink containers by docker-compose.yml).
"""
from pyflink.table import EnvironmentSettings, TableEnvironment

KAFKA_BOOTSTRAP = "kafka:9092"  # container-network address, not localhost
CASSANDRA_HOST = "cassandra"

SENSOR_SOURCE_DDL = f"""
CREATE TABLE sensor_readings_raw (
    vessel_id STRING,
    sensor_type STRING,
    reading_time TIMESTAMP(3),
    value DOUBLE,
    unit STRING,
    WATERMARK FOR reading_time AS reading_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'sensor-readings',
    'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
    'properties.group.id' = 'flink-warehouse-sensor',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json',
    'json.timestamp-format.standard' = 'ISO-8601'
)
"""

POSITION_SOURCE_DDL = f"""
CREATE TABLE position_reports_raw (
    vessel_id STRING,
    reading_time TIMESTAMP(3),
    latitude DOUBLE,
    longitude DOUBLE,
    speed_knots DOUBLE,
    heading_deg DOUBLE,
    WATERMARK FOR reading_time AS reading_time - INTERVAL '5' SECOND
) WITH (
    'connector' = 'kafka',
    'topic' = 'position-reports',
    'properties.bootstrap.servers' = '{KAFKA_BOOTSTRAP}',
    'properties.group.id' = 'flink-warehouse-position',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json',
    'json.timestamp-format.standard' = 'ISO-8601'
)
"""

# Sink DDLs mirror cassandra_schema.cql exactly — column names/types and the
# primary key must match the CQL table definition for the connector to write
# to the right partition/clustering columns.

SENSOR_READINGS_SINK_DDL = f"""
CREATE TABLE sensor_readings (
    vessel_id STRING,
    reading_date DATE,
    sensor_type STRING,
    reading_time TIMESTAMP(3),
    value DOUBLE,
    unit STRING,
    PRIMARY KEY (vessel_id, reading_date, sensor_type, reading_time) NOT ENFORCED
) WITH (
    'connector' = 'cassandra',
    'host' = '{CASSANDRA_HOST}',
    'port' = '9042',
    'keyspace' = 'ship_telemetry',
    'table' = 'sensor_readings'
)
"""

POSITION_REPORTS_SINK_DDL = f"""
CREATE TABLE position_reports (
    vessel_id STRING,
    reading_date DATE,
    reading_time TIMESTAMP(3),
    latitude DOUBLE,
    longitude DOUBLE,
    speed_knots DOUBLE,
    heading_deg DOUBLE,
    PRIMARY KEY (vessel_id, reading_date, reading_time) NOT ENFORCED
) WITH (
    'connector' = 'cassandra',
    'host' = '{CASSANDRA_HOST}',
    'port' = '9042',
    'keyspace' = 'ship_telemetry',
    'table' = 'position_reports'
)
"""

SENSOR_AGGREGATES_SINK_DDL = f"""
CREATE TABLE sensor_minute_aggregates (
    vessel_id STRING,
    sensor_type STRING,
    window_start TIMESTAMP(3),
    avg_value DOUBLE,
    min_value DOUBLE,
    max_value DOUBLE,
    sample_count BIGINT,
    PRIMARY KEY (vessel_id, sensor_type, window_start) NOT ENFORCED
) WITH (
    'connector' = 'cassandra',
    'host' = '{CASSANDRA_HOST}',
    'port' = '9042',
    'keyspace' = 'ship_telemetry',
    'table' = 'sensor_minute_aggregates'
)
"""

# Raw passthrough — the lake side. reading_date is derived from reading_time
# since the source stream doesn't carry a separate date field.
SENSOR_RAW_INSERT = """
INSERT INTO sensor_readings
SELECT vessel_id, CAST(reading_time AS DATE) AS reading_date, sensor_type, reading_time, value, unit
FROM sensor_readings_raw
"""

POSITION_RAW_INSERT = """
INSERT INTO position_reports
SELECT vessel_id, CAST(reading_time AS DATE) AS reading_date, reading_time, latitude, longitude, speed_knots, heading_deg
FROM position_reports_raw
"""

# Aggregated — the warehouse side.
AGGREGATION_INSERT = """
INSERT INTO sensor_minute_aggregates
SELECT
    vessel_id,
    sensor_type,
    window_start,
    AVG(value)   AS avg_value,
    MIN(value)   AS min_value,
    MAX(value)   AS max_value,
    COUNT(*)     AS sample_count
FROM TABLE(
    TUMBLE(TABLE sensor_readings_raw, DESCRIPTOR(reading_time), INTERVAL '1' MINUTE)
)
GROUP BY vessel_id, sensor_type, window_start
"""


def main() -> None:
    env = TableEnvironment.create(EnvironmentSettings.in_streaming_mode())

    for ddl in (
        SENSOR_SOURCE_DDL,
        POSITION_SOURCE_DDL,
        SENSOR_READINGS_SINK_DDL,
        POSITION_REPORTS_SINK_DDL,
        SENSOR_AGGREGATES_SINK_DDL,
    ):
        env.execute_sql(ddl)

    # One StatementSet so Flink reads each Kafka topic once and fans out to
    # all three sinks within a single job, rather than three separate jobs
    # each re-consuming the topic from scratch.
    statements = env.create_statement_set()
    statements.add_insert_sql(SENSOR_RAW_INSERT)
    statements.add_insert_sql(POSITION_RAW_INSERT)
    statements.add_insert_sql(AGGREGATION_INSERT)
    statements.execute().wait()


if __name__ == "__main__":
    main()
