"""warehouse/producer.py and warehouse/duckdb_writer.py with kafka and duckdb
replaced by in-memory fakes (neither is installed in CI)."""

import importlib
import json
import sys
import types
from datetime import datetime

import pytest


def load(monkeypatch, name, **fake_mods):
    """Import warehouse.<name> fresh against fake third-party modules, and
    restore sys.modules afterwards (monkeypatch undoes setitem/delitem)."""
    for mod_name, mod in fake_mods.items():
        monkeypatch.setitem(sys.modules, mod_name, mod)
    full = f"warehouse.{name}"
    monkeypatch.delitem(sys.modules, full, raising=False)
    return importlib.import_module(full)


@pytest.fixture
def producer(monkeypatch):
    sent, state = [], types.SimpleNamespace(closed=False, flushes=0, kwargs=None)

    class KP:
        def __init__(self, **kw):
            state.kwargs = kw

        def send(self, topic, value):
            sent.append((topic, value))

        def flush(self):
            state.flushes += 1

        def close(self):
            state.closed = True

    kafka = types.ModuleType("kafka")
    kafka.KafkaProducer = KP
    mod = load(monkeypatch, "producer", kafka=kafka)
    monkeypatch.setattr(mod.time, "sleep", lambda s: state.__dict__.setdefault("sleeps", []).append(s))
    return mod, sent, state


def test_make_reading_is_in_range_and_shaped(producer):
    mod = producer[0]
    for sensor, (lo, hi, unit) in mod.SENSORS.items():
        for _ in range(25):
            r = mod.make_reading("Dali", sensor)
            assert lo <= r["value"] <= hi
            assert r["unit"] == unit and r["vessel_id"] == "Dali" and r["sensor_type"] == sensor
            assert round(r["value"], 2) == r["value"]
            assert datetime.fromisoformat(r["reading_time"]).tzinfo is not None


def test_make_position_drifts_from_start(producer):
    mod = producer[0]
    p0 = mod.make_position("Dali", 0)
    lat0, lon0 = mod.START_POS["Dali"]
    assert (p0["latitude"], p0["longitude"]) == (lat0, lon0)  # tick 0: no drift
    p = mod.make_position("World Prize", 10)
    lat, lon = mod.START_POS["World Prize"]
    import math

    assert p["latitude"] == pytest.approx(lat + 0.01 * math.sin(10), abs=1e-5)
    assert p["longitude"] == pytest.approx(lon + 0.01 * math.cos(10), abs=1e-5)
    assert 8 <= p["speed_knots"] <= 18 and 0 <= p["heading_deg"] <= 359
    assert set(p) == {"vessel_id", "reading_time", "latitude", "longitude", "speed_knots", "heading_deg"}


def test_every_vessel_has_a_start_position(producer):
    mod = producer[0]
    assert set(mod.VESSELS) == set(mod.START_POS)


def test_main_publishes_ticks_then_closes(producer, monkeypatch, capsys):
    mod, sent, state = producer
    monkeypatch.setattr(sys, "argv", ["producer.py", "--ticks", "2", "--interval", "0.25",
                                      "--bootstrap", "kafka:9"])  # fmt: skip
    mod.main()
    n_vessels, n_sensors = len(mod.VESSELS), len(mod.SENSORS)
    readings = [s for s in sent if s[0] == "sensor-readings"]
    positions = [s for s in sent if s[0] == "position-reports"]
    assert len(readings) == 2 * n_vessels * n_sensors
    assert len(positions) == 2 * n_vessels
    assert state.flushes == 2 and state.closed is True
    assert state.sleeps == [0.25, 0.25]
    assert state.kwargs["bootstrap_servers"] == "kafka:9"
    assert json.loads(state.kwargs["value_serializer"]({"a": 1}).decode()) == {"a": 1}
    out = capsys.readouterr().out.splitlines()
    assert out == [
        f"tick 0: published {n_vessels * (n_sensors + 1)} messages",
        f"tick 1: published {n_vessels * (n_sensors + 1)} messages",
    ]


def test_main_zero_ticks_publishes_nothing_but_closes(producer, monkeypatch):
    mod, sent, state = producer
    monkeypatch.setattr(sys, "argv", ["producer.py", "--ticks", "0"])
    mod.main()
    assert sent == [] and state.closed is True and state.kwargs["bootstrap_servers"] == "localhost:9092"


def test_main_stops_cleanly_on_keyboard_interrupt(producer, monkeypatch):
    mod, sent, state = producer
    monkeypatch.setattr(mod.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(sys, "argv", ["producer.py"])
    mod.main()  # no --ticks: would run forever, interrupt ends it
    assert state.closed is True and len(sent) > 0


# ---- duckdb writer ----------------------------------------------------------------------------


@pytest.fixture
def writer(monkeypatch):
    state = types.SimpleNamespace(executed=[], messages=[], consumer_args=None, db=None)

    class Con:
        def execute(self, sql, params=None):
            state.executed.append((sql, params))

    class Consumer:
        def __init__(self, *topics, **kw):
            state.consumer_args = (topics, kw)

        def __iter__(self):
            return iter(state.messages)

    duck = types.ModuleType("duckdb")
    duck.connect = lambda path: state.__setattr__("db", path) or Con()
    kafka = types.ModuleType("kafka")
    kafka.KafkaConsumer = Consumer
    mod = load(monkeypatch, "duckdb_writer", duckdb=duck, kafka=kafka)
    return mod, state


def msg(topic, **row):
    return types.SimpleNamespace(topic=topic, value=row)


def test_writer_routes_messages_to_the_right_tables(writer, monkeypatch, capsys):
    mod, state = writer
    state.messages = [
        msg("sensor-readings", vessel_id="Dali", sensor_type="engine_rpm",
            reading_time="2026-01-02T03:04:05+00:00", value=77.5, unit="rpm"),
        msg("position-reports", vessel_id="Amadeus", reading_time="2026-01-02T03:04:06+00:00",
            latitude=56.5, longitude=-2.5, speed_knots=12.0, heading_deg=90.0),
    ]  # fmt: skip
    monkeypatch.setattr(sys, "argv", ["w.py", "--db", "/tmp/x.duckdb", "--bootstrap", "kk:1"])
    mod.main()
    assert state.db == "/tmp/x.duckdb"
    topics, kw = state.consumer_args
    assert topics == ("sensor-readings", "position-reports")
    assert kw["bootstrap_servers"] == "kk:1" and kw["auto_offset_reset"] == "earliest"
    assert kw["value_deserializer"](b'{"k": 2}') == {"k": 2}
    schema_sql, _ = state.executed[0]
    assert schema_sql == mod.SCHEMA_PATH.read_text()
    sensor_sql, sensor_params = state.executed[1]
    assert sensor_sql.startswith("INSERT INTO sensor_readings")
    assert sensor_params == ("Dali", "engine_rpm", datetime.fromisoformat("2026-01-02T03:04:05+00:00"),
                             77.5, "rpm")  # fmt: skip
    pos_sql, pos_params = state.executed[2]
    assert pos_sql.startswith("INSERT INTO position_reports")
    assert pos_params == ("Amadeus", datetime.fromisoformat("2026-01-02T03:04:06+00:00"), 56.5, -2.5, 12.0, 90.0)
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("listening for sensor-readings and position-reports -> /tmp/x.duckdb")
    assert out[1:] == ["wrote sensor-readings row for Dali", "wrote position-reports row for Amadeus"]


def test_writer_default_db_and_bootstrap(writer, monkeypatch):
    mod, state = writer
    monkeypatch.setattr(sys, "argv", ["w.py"])
    mod.main()
    assert state.db == str(mod.DEFAULT_DB)
    assert state.consumer_args[1]["bootstrap_servers"] == "localhost:9092"
    assert len(state.executed) == 1  # schema only, no messages
