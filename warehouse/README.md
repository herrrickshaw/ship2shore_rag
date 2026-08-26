# Ship telemetry data lake / warehouse

A separate concern from everything else in this repo: the Postgres `ops`
module and the RAG literature corpus are both low-frequency, structured
data. This is the opposite shape — potentially thousands of sensor readings
per vessel per day (engine RPM, fuel flow, exhaust temp, shaft power, GPS
position) — the kind of write-heavy, mostly-append workload Cassandra is
built for and Postgres is not.

```
                                    +--> sensor_readings      (raw, lake)
producer.py --(JSON)--> Kafka --> Flink --> position_reports    (raw, lake)
                                    +--> sensor_minute_aggregates (warehouse)
```

One Flink job (a `StatementSet` — see `flink_job.py`), reading each Kafka
topic once, fanning out to three Cassandra sinks: two raw passthroughs and
one 1-minute tumbling-window aggregation. Not three separate jobs each
re-consuming the topic from scratch.

- **Kafka** — the message bus. KRaft mode (no separate ZooKeeper — Kafka 3.x+
  doesn't need it, and it's meaningfully lighter for a single-node dev setup).
- **Flink** — the stream processor, doing both jobs at once: raw passthrough
  (nothing is lost even before any aggregation) and 1-minute avg/min/max/count
  per vessel per sensor.
- **Cassandra** — the lake/warehouse. `sensor_readings` and
  `position_reports` are the lake (raw, as-received); `sensor_minute_aggregates`
  is the warehouse side (pre-aggregated, fast to query).

## Running it

This is genuinely heavy — four JVM-based containers (Kafka, Cassandra, Flink
jobmanager + taskmanager). `docker-compose.yml` caps each service's memory
(Kafka 512MB, Cassandra 2GB, each Flink node 1GB — roughly 4.5GB total; the
first, lower memory budget this project tried made Cassandra crash outright
and made Flink fail to start at all, both fixed by raising these numbers —
see the "Honest scope" note below on what that means for running all four
at once) for exactly this reason: **on an 8GB Mac, this is a real resource
commitment**, especially alongside Postgres and the RAG side's embedding
model already running. Stop other heavy local services first if things feel
sluggish.

```bash
cd warehouse
podman machine start   # or `docker` if you have Docker Desktop instead of podman
podman-compose up -d   # or `docker compose up -d`

# apply the Cassandra schema once the container is healthy (can take ~30-60s
# on first boot)
podman exec -i s2s-cassandra cqlsh < cassandra_schema.cql

# start the simulated telemetry feed
pip install kafka-python
python3 producer.py --interval 2   # one tick of ~25 messages every 2s

# submit the Flink aggregation job — needs the Kafka + Cassandra SQL
# connector JARs on Flink's classpath first (not bundled in the base image):
#   https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.19/
#   https://repo.maven.apache.org/maven2/org/apache/flink/flink-connector-cassandra/3.2.0-1.19/
# drop both JARs into a local jars/ dir, add a volume mount for it in
# docker-compose.yml (both flink-jobmanager and flink-taskmanager:
#   volumes: ["./jars:/opt/flink/lib/custom"]), restart the Flink containers,
# then:
podman exec -i s2s-flink-jobmanager ./bin/flink run -py /opt/flink_job.py
# (mount flink_job.py into the jobmanager container too, or copy it in first)
```

## Honest scope

- **The pieces are individually verified, live, in this environment — the
  full pipeline (Flink SQL job + connector JARs) is not.** What's actually
  been run and confirmed working on this machine: Cassandra accepts the
  schema and real writes/reads via `cqlsh`; Kafka accepts and serves real
  producer traffic (checked with the console consumer); Flink's jobmanager
  and taskmanager register with each other cleanly. What hasn't: submitting
  `flink_job.py` itself against a live cluster, which needs the Kafka +
  Cassandra SQL connector JARs wired onto the classpath (see "Running it"
  above) — that step is documented but not yet automated or run end-to-end
  here. Treat the SQL in `flink_job.py` as carefully written and consistent
  with the schema it targets (every column/type/primary-key matches
  `cassandra_schema.cql` exactly), not as proven-by-execution.
- **Single-node everything.** Kafka (1 broker), Cassandra (1 node), Flink (1
  task manager, 2 slots). None of this has the replication/fault-tolerance a
  production telemetry pipeline would need — this is a demo/dev-scale
  architecture demonstrating the pattern, not a production system.
- **Synthetic data.** `producer.py` generates plausible-looking but entirely
  made-up sensor values — there's no real engine/GPS hardware behind any of
  this, and the vessel names (drawn from the real casualty reports already
  in this project's literature corpus) don't imply the telemetry itself is
  real.
