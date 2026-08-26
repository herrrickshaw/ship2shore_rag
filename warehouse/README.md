# Ship telemetry data lake / warehouse

A separate concern from everything else in this repo: the Postgres `ops`
module and the RAG literature corpus are both low-frequency, structured
data. This is the opposite shape — potentially thousands of sensor readings
per vessel per day (engine RPM, fuel flow, exhaust temp, shaft power, GPS
position) — write-heavy and mostly-append.

```
producer.py --(JSON)--> Kafka --> duckdb_writer.py --> ship_telemetry.duckdb
                                                          - sensor_readings        (raw, lake)
                                                          - position_reports       (raw, lake)
                                                          - sensor_minute_aggregates (SQL view, warehouse)
```

- **Kafka** — the message bus. KRaft mode (no separate ZooKeeper). Simulates
  a realistic ingest path (decoupled producer/consumer, replay from offset)
  without pretending this needs to survive a broker outage.
- **DuckDB** — the lake *and* the warehouse: one embedded file, no server.
  `sensor_readings` / `position_reports` are the raw lake tables;
  `sensor_minute_aggregates` is a SQL view (`time_bucket` + `GROUP BY`) over
  the raw table — no separate aggregation job, computed at query time.

## Why DuckDB, not Cassandra/Flink

The original version of this ran Kafka + Flink + Cassandra: four JVM
containers, ~4.5GB RAM budget, and a real dead end — Flink's official
Cassandra connector (`flink-connector-cassandra`) has no Table API/SQL
factory (verified by inspecting the JAR's `META-INF/services` — no
`org.apache.flink.table.factories.Factory` registration), so the natural
`CREATE TABLE ... WITH ('connector' = 'cassandra', ...)` sink doesn't exist
to use. Working around that meant a DataStream-API job with a hand-written
Python sink function, on top of memory tuning that had already been fought
once (Cassandra OOMing at 768m heap, Flink refusing to start under ~768m
process size for JVM-overhead reasons).

None of that complexity is buying anything here. Every other repo in this
account that accumulates readings over time and queries them
(`global-market-data`, `global-stock-screener`, `agri-commodity-tracker`,
`market-correlation-matrices`) uses a plain embedded file — DuckDB or
Parquet, no server, no cluster, no daemon to keep running or resource-tune —
and there's no reason a single-vessel-simulator demo on one machine should
be the exception. Kafka stays (it's genuinely demonstrating a real ingest
pattern, and it's one lightweight container); Cassandra and Flink are gone.

## Running it

```bash
cd warehouse
podman machine start   # or `docker` if you have Docker Desktop instead of podman
podman-compose up -d   # or `docker compose up -d` — just Kafka now

pip install -r ../requirements-warehouse.txt

# start the simulated telemetry feed
python3 producer.py --interval 2   # one tick of ~25 messages every 2s

# in another terminal: consume both topics, write straight into DuckDB
python3 duckdb_writer.py

# query it — no server, just open the file
python3 -c "
import duckdb
con = duckdb.connect('ship_telemetry.duckdb')
print(con.execute('SELECT COUNT(*) FROM sensor_readings').fetchone())
print(con.execute('SELECT * FROM sensor_minute_aggregates LIMIT 5').fetchdf())
"
```

`ship_telemetry.duckdb` is gitignored (it's local run output, same policy as
`data/*.duckdb` files elsewhere in this account) — `schema.sql` is the
source of truth and is re-applied idempotently (`CREATE TABLE IF NOT
EXISTS`) every time `duckdb_writer.py` starts.

## Honest scope

- **Single-node Kafka**, 1 broker, 1 partition per topic — a dev-scale
  message bus, not a cluster.
- **Synthetic data.** `producer.py` generates plausible-looking but entirely
  made-up sensor values — there's no real engine/GPS hardware behind any of
  this, and the vessel names (drawn from the real casualty reports already
  in this project's literature corpus) don't imply the telemetry itself is
  real.
- **`sensor_minute_aggregates` is a view, not a materialized table** —
  recomputed on every query. Fine at demo volume; if raw-row count ever grew
  large enough for that to matter, the fix is a periodic `CREATE TABLE ...
  AS SELECT` snapshot, not bringing back a stream processor.
