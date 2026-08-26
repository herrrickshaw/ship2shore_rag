# Ship telemetry data lake / warehouse

A separate concern from everything else in this repo: the Postgres `ops`
module and the RAG literature corpus are both low-frequency, structured
data. This is the opposite shape — potentially thousands of sensor readings
per vessel per day (engine RPM, fuel flow, exhaust temp, shaft power, GPS
position) — the kind of write-heavy, mostly-append workload Cassandra is
built for and Postgres is not.

```
producer.py --(JSON)--> Kafka (KRaft, single broker) --> Flink (1-min tumbling
windows) --> Cassandra (raw readings + pre-aggregated rollups)
```

- **Kafka** — the message bus. KRaft mode (no separate ZooKeeper — Kafka 3.x+
  doesn't need it, and it's meaningfully lighter for a single-node dev setup).
- **Flink** — the stream processor. Consumes raw readings, computes 1-minute
  avg/min/max/count per vessel per sensor, writes the aggregate to Cassandra.
  Raw readings also get written straight to Cassandra by a second (simpler)
  path so nothing is lost even before aggregation runs — see "Two write
  paths" below.
- **Cassandra** — the lake/warehouse. `sensor_readings` and
  `position_reports` are the lake (raw, as-received); `sensor_minute_aggregates`
  is the warehouse side (pre-aggregated, fast to query).

## Running it

This is genuinely heavy — four JVM-based containers (Kafka, Cassandra, Flink
jobmanager + taskmanager). `docker-compose.yml` caps each service's memory
(Kafka 512MB, Cassandra 1GB, each Flink node 640MB — roughly 2.8GB total) for
exactly this reason: **on an 8GB Mac, this is a real resource commitment**,
especially alongside Postgres and the RAG side's embedding model already
running. Stop other heavy local services first if things feel sluggish.

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

## Two write paths — raw vs. aggregated

The producer publishes to Kafka; Flink reads from Kafka and writes only the
*aggregated* rollups to Cassandra per `flink_job.py`. Raw readings landing
directly in `sensor_readings`/`position_reports` (the actual "lake" tables)
isn't wired up in `flink_job.py` — that would be a second Flink sink (or a
simpler Kafka Connect Cassandra sink) inserting the untransformed stream
alongside the aggregation job. Not built yet; flagged here rather than
implied as done, since "the lake has raw data" and "the warehouse has
aggregates" are both claims this README makes about the schema, but only the
aggregate path is currently wired end-to-end in code.

## Honest scope

- **Not verified end-to-end in this environment.** Bringing up four JVM
  containers plus wiring Flink's Kafka/Cassandra connectors correctly is a
  substantial undertaking even before touching the 8GB RAM ceiling on this
  particular machine. The compose stack, schema, producer, and Flink job are
  real, reviewable code — treat "does this actually run cleanly end-to-end"
  as unverified until you've run it yourself (or I have, on a beefier box).
- **Single-node everything.** Kafka (1 broker), Cassandra (1 node), Flink (1
  task manager, 2 slots). None of this has the replication/fault-tolerance a
  production telemetry pipeline would need — this is a demo/dev-scale
  architecture demonstrating the pattern, not a production system.
- **Synthetic data.** `producer.py` generates plausible-looking but entirely
  made-up sensor values — there's no real engine/GPS hardware behind any of
  this, and the vessel names (drawn from the real casualty reports already
  in this project's literature corpus) don't imply the telemetry itself is
  real.
