"""Kafka -> DuckDB. Reads both telemetry topics and appends every message to
the lake tables (schema.sql) in a single embedded file — no cluster, no JVM,
no separate stream processor. The earlier design used Flink for a windowed
aggregation and Cassandra as the sink; both are gone. DuckDB computes the
1-minute aggregate (sensor_minute_aggregates) as a plain SQL view over the
raw table at query time instead, which is fast enough at this volume that a
standing aggregation job isn't worth the extra moving part — matching how
this project's other repos (global-market-data, agri-commodity-tracker,
market-correlation-matrices) handle accumulate-then-query data: one process,
one file, plain SQL.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import duckdb
from kafka import KafkaConsumer

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DEFAULT_DB = Path(__file__).parent / "ship_telemetry.duckdb"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="path to the DuckDB file")
    args = parser.parse_args()

    con = duckdb.connect(args.db)
    con.execute(SCHEMA_PATH.read_text())

    consumer = KafkaConsumer(
        "sensor-readings",
        "position-reports",
        bootstrap_servers=args.bootstrap,
        auto_offset_reset="earliest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )

    print(f"listening for sensor-readings and position-reports -> {args.db}")
    for msg in consumer:
        row = msg.value
        reading_time = datetime.fromisoformat(row["reading_time"])
        if msg.topic == "sensor-readings":
            con.execute(
                "INSERT INTO sensor_readings (vessel_id, sensor_type, reading_time, value, unit) "
                "VALUES (?, ?, ?, ?, ?)",
                (row["vessel_id"], row["sensor_type"], reading_time, row["value"], row["unit"]),
            )
        else:  # position-reports
            con.execute(
                "INSERT INTO position_reports (vessel_id, reading_time, latitude, longitude, speed_knots, heading_deg) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    row["vessel_id"],
                    reading_time,
                    row["latitude"],
                    row["longitude"],
                    row["speed_knots"],
                    row["heading_deg"],
                ),
            )
        print(f"wrote {msg.topic} row for {row['vessel_id']}")


if __name__ == "__main__":
    main()
