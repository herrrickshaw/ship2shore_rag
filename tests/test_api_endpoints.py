"""The REST routes not exercised by tests/test_api.py: crew, logs, equipment,
parts, maintenance, fuel, procurement, drydock, safety, fleet."""

from datetime import date, timedelta

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
from ops import store  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(store, "OPS_SQLITE_PATH", str(tmp_path / "api.sqlite3"))
    c = TestClient(api.app, headers={"X-API-Key": api.API_KEY})
    c.post("/users", json={"name": "Cap", "role": "master", "email": "c@x.io"})
    c.post("/users", json={"name": "Chief", "role": "chief_engineer"})
    c.post("/users", json={"name": "Deck", "role": "deck_crew"})
    assert c.post("/vessels", json={"name": "MV Test", "imo_number": "1111111", "flag": "PA",
                                    "gross_tonnage": 1234.5}, headers={"X-User": "Cap"}).json() == {"id": 1}  # fmt: skip
    return c


CAP = {"X-User": "Cap"}
CHIEF = {"X-User": "Chief"}
DECK = {"X-User": "Deck"}


def test_users_roundtrip_and_invalid_role(client):
    users = client.get("/users").json()
    assert [u["name"] for u in users] == ["Cap", "Chief", "Deck"]
    assert users[0]["email"] == "c@x.io"
    assert client.post("/users", json={"name": "X", "role": "pirate"}).status_code == 422


def test_get_vessel_by_name_and_imo_and_extra_fields(client):
    by_imo = client.get("/vessels/1111111").json()
    by_name = client.get("/vessels/MV Test").json()
    assert by_imo == by_name and by_imo["flag"] == "PA" and by_imo["gross_tonnage"] == 1234.5
    r = client.get("/vessels/nope")
    assert r.status_code == 404 and "no vessel matching 'nope'" in r.json()["detail"]


def test_crew_lifecycle_and_filters(client):
    body = {"name": "Jane", "rank": "Master", "vessel": "MV Test", "nationality": "IN",
            "stcw_cert_number": "C9", "stcw_cert_expiry": "2027-01-01", "sign_on_date": "2026-01-01"}  # fmt: skip
    assert client.post("/crew", json=body, headers=CAP).json() == {"id": 1}
    assert client.post("/crew", json=body, headers=DECK).status_code == 403
    assert client.post("/crew", json={**body, "vessel": "ghost"}, headers=CAP).status_code == 404
    client.post("/vessels", json={"name": "MV Two"}, headers=CAP)
    client.post("/crew", json={**body, "name": "Bob", "vessel": "MV Two"}, headers=CAP)
    assert len(client.get("/crew").json()) == 2
    only = client.get("/crew", params={"vessel": "MV Two"}).json()
    assert [c["name"] for c in only] == ["Bob"]
    assert client.get("/crew", params={"vessel": "ghost"}).status_code == 404
    assert client.post("/crew/1/signoff", json={"sign_off_date": "2026-06-01"},
                       headers=DECK).status_code == 403  # fmt: skip
    assert client.post(
        "/crew/1/signoff", json={"sign_off_date": "2026-06-01"}, headers=CAP
    ).json() == {"ok": True}
    jane = next(c for c in client.get("/crew").json() if c["name"] == "Jane")
    assert jane["sign_off_date"] == "2026-06-01"
    assert (
        client.post("/crew/1/signoff", json={"sign_off_date": "garbage"}, headers=CAP).status_code
        == 422
    )


def test_log_entries_flow_and_gates(client):
    r = client.post("/vessels/MV Test/log", json={"log_type": "captain", "entry_text": "All fine",
                                                  "latitude": 1.5, "longitude": 2.5}, headers=CAP)  # fmt: skip
    assert r.json() == {"id": 1}
    assert client.post("/vessels/MV Test/log", json={"log_type": "deck", "entry_text": "w"},
                       headers=DECK).status_code == 200  # fmt: skip
    assert client.post("/vessels/MV Test/log", json={"log_type": "captain", "entry_text": "x"},
                       headers=DECK).status_code == 403  # fmt: skip
    assert client.post("/vessels/ghost/log", json={"log_type": "deck", "entry_text": "x"},
                       headers=CAP).status_code == 404  # fmt: skip
    rows = client.get("/vessels/MV Test/log").json()
    assert len(rows) == 2
    cap = next(x for x in rows if x["log_type"] == "captain")
    assert (cap["latitude"], cap["longitude"], cap["logged_by"]) == (1.5, 2.5, 1)
    only = client.get("/vessels/MV Test/log", params={"log_type": "deck"}).json()
    assert [x["entry_text"] for x in only] == ["w"]
    assert client.get("/vessels/MV Test/log", params={"log_type": "bogus"}).status_code == 422


def test_equipment_parts_maintenance(client):
    assert client.post("/vessels/MV Test/equipment", json={"name": "ME", "manufacturer": "MAN",
                       "model": "6S60", "equipment_type": "diesel", "serial_number": "S1"},
                       headers=CHIEF).json() == {"id": 1}  # fmt: skip
    assert (
        client.post("/vessels/MV Test/equipment", json={"name": "X"}, headers=DECK).status_code
        == 403
    )
    eq = client.get("/vessels/MV Test/equipment").json()
    assert eq[0]["name"] == "ME" and eq[0]["model"] == "6S60"
    assert client.post("/equipment/1/parts", json={"part_number": "P1", "part_name": "Liner",
                       "manufacturer": "MAN", "stock_quantity": 3}, headers=CHIEF).json() == {"id": 1}  # fmt: skip
    assert client.post("/equipment/1/parts", json={"part_number": "P9", "part_name": "n"},
                       headers=DECK).status_code == 403  # fmt: skip
    parts = client.get("/equipment/1/parts").json()
    assert parts[0]["part_number"] == "P1" and parts[0]["stock_quantity"] == 3
    m = {
        "job_type": "breakdown",
        "description": "Cracked",
        "running_hours": 10.5,
        "parts_used": "P1",
    }
    assert client.post("/equipment/1/maintenance", json=m, headers=CHIEF).json() == {"id": 1}
    assert client.post("/equipment/1/maintenance", json=m, headers=DECK).status_code == 403
    assert client.post("/equipment/1/maintenance", json={**m, "job_type": "nap"},
                       headers=CHIEF).status_code == 422  # fmt: skip
    got = client.get("/equipment/1/maintenance").json()
    assert got[0]["running_hours"] == 10.5 and got[0]["performed_by"] == 2


def test_fuel_and_procurement(client):
    f = {"fuel_type": "VLSFO", "event_type": "bunkering", "quantity_mt": 250.5, "rob_after_mt": 300,
         "location": "Fujairah"}  # fmt: skip
    assert client.post("/vessels/MV Test/fuel", json=f, headers=CHIEF).json() == {"id": 1}
    assert client.post("/vessels/MV Test/fuel", json=f, headers=DECK).status_code == 403
    assert client.post("/vessels/MV Test/fuel", json={**f, "event_type": "x"},
                       headers=CHIEF).status_code == 422  # fmt: skip
    fuel = client.get("/vessels/MV Test/fuel").json()
    assert fuel[0]["quantity_mt"] == 250.5 and fuel[0]["location"] == "Fujairah"

    po = {"items": "liner x2", "supplier": "Acme", "total_cost": 99.5, "currency": "USD",
          "expected_delivery": "2026-12-01", "equipment_id": None}  # fmt: skip
    assert client.post("/vessels/MV Test/procurement", json=po, headers=CHIEF).json() == {"id": 1}
    assert client.post("/vessels/MV Test/procurement", json=po, headers=DECK).status_code == 403
    listed = client.get("/vessels/MV Test/procurement").json()
    assert listed[0]["status"] == "requested" and listed[0]["supplier"] == "Acme"
    assert client.get("/vessels/MV Test/procurement", params={"status": "approved"}).json() == []
    assert client.post("/procurement/1/approve", headers=DECK).status_code == 403
    assert client.post("/procurement/1/approve", headers=CAP).json() == {"ok": True}
    assert (
        client.get("/vessels/MV Test/procurement", params={"status": "approved"}).json()[0]["id"]
        == 1
    )
    assert (
        client.patch("/procurement/1/status", json={"status": "received"}, headers=DECK).status_code
        == 403
    )
    assert client.patch(
        "/procurement/1/status", json={"status": "received"}, headers=CAP
    ).json() == {"ok": True}
    assert (
        client.patch("/procurement/1/status", json={"status": "lost"}, headers=CAP).status_code
        == 422
    )
    assert client.get("/vessels/MV Test/procurement").json()[0]["status"] == "received"


def test_drydock_endpoints(client):
    d = {"yard": "Yard", "location": "Dubai", "planned_start": "2027-01-10", "planned_end": "2027-02-10",
         "scope_description": "Paint", "total_cost": 5.0, "currency": "USD"}  # fmt: skip
    assert client.post("/vessels/MV Test/drydock", json=d, headers=CAP).json() == {"id": 1}
    assert client.post("/vessels/MV Test/drydock", json=d, headers=DECK).status_code == 403
    assert client.post("/vessels/MV Test/drydock", headers=CAP).json() == {"id": 2}  # body optional
    rows = client.get("/vessels/MV Test/drydock").json()
    assert len(rows) == 2
    full = next(r for r in rows if r["yard"] == "Yard")
    assert full["planned_start"] == "2027-01-10" and full["status"] == "planned"
    assert client.get("/vessels/ghost/drydock").status_code == 404


def test_safety_endpoints_and_find_similar(client, monkeypatch):
    import rag.similar_incidents as si

    seen = []
    monkeypatch.setattr(si, "find_similar_incidents", lambda d: seen.append(d) or [{"title": "T"}])
    body = {"incident_type": "incident", "description": "Fire", "severity": "critical"}
    assert client.post("/vessels/MV Test/safety", json=body).json() == {"id": 1}
    assert seen == []  # opt-in only
    r = client.post("/vessels/MV Test/safety", params={"find_similar": "true"},
                    json={"incident_type": "near_miss", "description": "Slip"}, headers=DECK)  # fmt: skip
    assert r.json() == {"id": 2, "similar": [{"title": "T"}]} and seen == ["Slip"]
    assert (
        client.post("/vessels/MV Test/safety", json={**body, "severity": "huge"}).status_code == 422
    )
    assert len(client.get("/vessels/MV Test/safety").json()) == 2
    assert client.get("/vessels/MV Test/safety", params={"status": "closed"}).json() == []
    assert client.get("/vessels/MV Test/safety", params={"status": "open"}).json() != []
    reportable = client.get("/safety/reportable").json()
    assert [x["description"] for x in reportable] == ["Fire"]
    assert (
        client.post(
            "/safety/1/close", json={"corrective_action": "Fixed"}, headers=DECK
        ).status_code
        == 403
    )
    assert client.post(
        "/safety/1/close", json={"corrective_action": "Fixed"}, headers=CAP
    ).json() == {"ok": True}
    assert client.get("/safety/reportable").json() == []
    closed = client.get("/vessels/MV Test/safety", params={"status": "closed"}).json()
    assert closed[0]["corrective_action"] == "Fixed" and closed[0]["closed_by"] == 1


def test_fleet_status_endpoint_windows(client):
    soon = (date.today() + timedelta(days=5)).isoformat()
    client.post("/crew", json={"name": "J", "rank": "Cook", "vessel": "MV Test",
                               "stcw_cert_expiry": soon}, headers=CAP)  # fmt: skip
    client.post("/vessels/MV Test/safety", json={"incident_type": "incident", "description": "d",
                                                 "severity": "high"})  # fmt: skip
    client.post("/vessels/MV Test/drydock", json={"planned_start": (date.today() + timedelta(days=45)).isoformat()},
                headers=CAP)  # fmt: skip
    s = client.get("/fleet/status").json()
    assert s["vessel_count"] == 1
    assert s["open_incidents_by_severity"] == {"high": 1}
    assert len(s["certs_expiring"]) == 1 and len(s["drydocks_upcoming"]) == 1
    s = client.get("/fleet/status", params={"cert_days": 1, "drydock_days": 10}).json()
    assert s["certs_expiring"] == [] and s["drydocks_upcoming"] == []
