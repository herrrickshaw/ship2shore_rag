# Changelog

## [Unreleased] — 2026-08-26 — Telemetry warehouse: Cassandra+Flink -> DuckDB

### Changed
- **`warehouse/`** — replaced the Cassandra + Flink stack with DuckDB for the
  ship telemetry data lake/warehouse.

### Removed
- **Flink** (`flink_job.py`, `Dockerfile.flink`, `jars/`) and **Cassandra**
  (`cassandra_schema.cql`, `cassandra_writer.py`) — Flink's official
  Cassandra connector (`flink-connector-cassandra_2.12`) turned out to have
  no Table API/SQL factory (verified directly: no
  `org.apache.flink.table.factories.Factory` entry in the JAR's
  `META-INF/services/`), so the natural `CREATE TABLE ... WITH ('connector'
  = 'cassandra', ...)` sink used throughout the original design doesn't
  exist to use. Working around that (DataStream API + a hand-written Python
  sink) added real complexity on top of memory tuning already fought once —
  Cassandra OOMing under 1024m heap, Flink refusing to start under ~768m
  process size — for a demo-scale, single-vessel-simulator telemetry feed
  that didn't need a clustered database in the first place.

### Added
- **`warehouse/schema.sql` + `warehouse/duckdb_writer.py`** — a single
  embedded DuckDB file (`ship_telemetry.duckdb`, gitignored) written
  directly by a plain Kafka consumer. The 1-minute windowed aggregation that
  Flink used to compute is now a SQL view (`time_bucket` + `GROUP BY`) over
  the raw table, recomputed at query time — no standing stream-processing
  job. This matches how every other repo in this account that accumulates
  readings over time and queries them handles it (`global-market-data`,
  `global-stock-screener`, `agri-commodity-tracker`,
  `market-correlation-matrices` all use a plain embedded file — DuckDB or
  Parquet — instead of a clustered database).
- **`requirements-warehouse.txt`** — scoped deps (`kafka-python`,
  `duckdb`) for the warehouse scripts, mirroring the existing
  `requirements-api.txt` pattern.

Kafka stays (KRaft mode, single container) — it's still doing real work
(decoupling the simulated producer from the consumer, replay-from-offset),
just no longer feeding a JVM cluster on the other end. Verified live:
producer -> Kafka -> `duckdb_writer.py`, 125 messages in, 100
`sensor_readings` + 25 `position_reports` out (exact match), aggregate view
correct (`sample_count=5` per vessel/sensor across 5 ticks).
