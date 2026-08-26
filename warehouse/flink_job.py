"""PyFlink job: Kafka (raw sensor readings) -> 1-minute tumbling window
aggregation -> Cassandra (sensor_minute_aggregates). This is the "warehouse"
transformation — turning a high-frequency raw stream into a pre-aggregated
table that's actually pleasant to query, sitting between the Kafka data bus
and the Cassandra data lake.

Requires the Flink Kafka and Cassandra SQL connector JARs on the classpath —
see warehouse/README.md for exact versions and where to put them (jars/,
mounted into the Flink containers by docker-compose.yml).
"""
from pyflink.table import EnvironmentSettings, TableEnvironment

KAFKA_BOOTSTRAP = "kafka:9092"  # container-network address, not localhost
CASSANDRA_HOST = "cassandra"

SOURCE_DDL = f"""
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
    'properties.group.id' = 'flink-warehouse',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json',
    'json.timestamp-format.standard' = 'ISO-8601'
)
"""

SINK_DDL = f"""
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

AGGREGATION_QUERY = """
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
    env.execute_sql(SOURCE_DDL)
    env.execute_sql(SINK_DDL)
    env.execute_sql(AGGREGATION_QUERY).wait()


if __name__ == "__main__":
    main()
