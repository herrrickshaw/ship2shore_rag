"""Simulates ship sensor telemetry and publishes it to Kafka — standing in for
real engine/GPS sensors so the Flink -> Cassandra pipeline has something to
process. Vessel names match the ones already seeded in the Postgres ops
module (see tests/seed data) so the two sides of the project reference the
same fleet, but this is synthetic telemetry, not real sensor data.
"""
import argparse
import json
import math
import random
import time
from datetime import datetime, timezone

from kafka import KafkaProducer

VESSELS = ["Dali", "Baylor J. Tregre", "World Prize", "Amadeus", "Jacoba"]

SENSORS = {
    "engine_rpm": (60, 90, "rpm"),
    "fuel_flow_lph": (150, 400, "L/h"),
    "exhaust_temp_c": (300, 420, "C"),
    "shaft_power_kw": (2000, 9000, "kW"),
}

# Rough starting positions so movement looks plausible, not physically real.
START_POS = {
    "Dali": (39.2, -76.5),
    "Baylor J. Tregre": (29.0, -90.0),
    "World Prize": (59.3, 19.0),
    "Amadeus": (56.5, -2.5),
    "Jacoba": (55.5, -1.9),
}


def make_reading(vessel: str, sensor_type: str) -> dict:
    lo, hi, unit = SENSORS[sensor_type]
    value = round(random.uniform(lo, hi), 2)
    return {
        "vessel_id": vessel,
        "sensor_type": sensor_type,
        "reading_time": datetime.now(timezone.utc).isoformat(),
        "value": value,
        "unit": unit,
    }


def make_position(vessel: str, tick: int) -> dict:
    lat0, lon0 = START_POS[vessel]
    drift = tick * 0.001
    return {
        "vessel_id": vessel,
        "reading_time": datetime.now(timezone.utc).isoformat(),
        "latitude": round(lat0 + drift * math.sin(tick), 5),
        "longitude": round(lon0 + drift * math.cos(tick), 5),
        "speed_knots": round(random.uniform(8, 18), 1),
        "heading_deg": round(random.uniform(0, 359), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--interval", type=float, default=1.0, help="seconds between ticks")
    parser.add_argument("--ticks", type=int, default=None, help="stop after N ticks (default: run forever)")
    args = parser.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )

    tick = 0
    try:
        while args.ticks is None or tick < args.ticks:
            for vessel in VESSELS:
                for sensor_type in SENSORS:
                    producer.send("sensor-readings", make_reading(vessel, sensor_type))
                producer.send("position-reports", make_position(vessel, tick))
            producer.flush()
            print(f"tick {tick}: published {len(VESSELS) * (len(SENSORS) + 1)} messages")
            tick += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        producer.close()


if __name__ == "__main__":
    main()
