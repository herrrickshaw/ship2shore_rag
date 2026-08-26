import os
import tempfile
from datetime import date, timedelta

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
from ops import store  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.remove(path)
    monkeypatch.setattr(store, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(store, "OPS_SQLITE_PATH", path)
    yield TestClient(api.app, headers={"X-API-Key": api.API_KEY})
    if os.path.exists(path):
        os.remove(path)


def test_missing_api_key_denied(client):
    resp = client.get("/vessels", headers={"X-API-Key": ""})
    assert resp.status_code == 401


def test_wrong_api_key_denied(client):
    resp = client.get("/vessels", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_vessel_add_denied_for_deck_crew(client):
    client.post("/users", json={"name": "Deck Hand", "role": "deck_crew"})
    resp = client.post(
        "/vessels",
        json={"name": "MV Test", "imo_number": "1111111"},
        headers={"X-User": "Deck Hand"},
    )
    assert resp.status_code == 403


def test_vessel_add_allowed_for_master(client):
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    resp = client.post(
        "/vessels",
        json={"name": "MV Test", "imo_number": "1111111"},
        headers={"X-User": "Captain Ahab"},
    )
    assert resp.status_code == 200
    assert client.get("/vessels").json()[0]["name"] == "MV Test"


def test_captain_log_requires_master(client):
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    client.post("/users", json={"name": "Deck Hand", "role": "deck_crew"})
    client.post("/vessels", json={"name": "MV Test"}, headers={"X-User": "Captain Ahab"})

    denied = client.post(
        "/vessels/MV Test/log",
        json={"log_type": "captain", "entry_text": "..."},
        headers={"X-User": "Deck Hand"},
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/vessels/MV Test/log",
        json={"log_type": "captain", "entry_text": "Departed port."},
        headers={"X-User": "Captain Ahab"},
    )
    assert allowed.status_code == 200


def test_safety_report_unrestricted(client):
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    client.post("/users", json={"name": "Deck Hand", "role": "deck_crew"})
    client.post("/vessels", json={"name": "MV Test"}, headers={"X-User": "Captain Ahab"})
    resp = client.post(
        "/vessels/MV Test/safety",
        json={"incident_type": "near_miss", "description": "Loose grating"},
        headers={"X-User": "Deck Hand"},
    )
    assert resp.status_code == 200
    assert client.get("/vessels/MV Test/safety").json()[0]["status"] == "open"


def test_procurement_approval_workflow(client):
    client.post("/users", json={"name": "Chief Engineer", "role": "chief_engineer"})
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    client.post("/vessels", json={"name": "MV Test"}, headers={"X-User": "Captain Ahab"})

    create = client.post(
        "/vessels/MV Test/procurement",
        json={"items": "PN-1 Fuel injector x2"},
        headers={"X-User": "Chief Engineer"},
    )
    po_id = create.json()["id"]
    assert client.get("/vessels/MV Test/procurement").json()[0]["status"] == "requested"

    denied = client.post(f"/procurement/{po_id}/approve", headers={"X-User": "Chief Engineer"})
    assert denied.status_code == 403

    approved = client.post(f"/procurement/{po_id}/approve", headers={"X-User": "Captain Ahab"})
    assert approved.status_code == 200
    assert client.get("/vessels/MV Test/procurement").json()[0]["status"] == "approved"


def test_unknown_vessel_returns_404(client):
    resp = client.get("/vessels/does-not-exist")
    assert resp.status_code == 404


def test_duplicate_imo_returns_clean_409_not_raw_500(client):
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    client.post(
        "/vessels",
        json={"name": "MV One", "imo_number": "1234567"},
        headers={"X-User": "Captain Ahab"},
    )
    resp = client.post(
        "/vessels",
        json={"name": "MV Two", "imo_number": "1234567"},
        headers={"X-User": "Captain Ahab"},
    )
    assert resp.status_code == 409
    assert "detail" in resp.json()


def test_safety_close_with_no_body_still_authorizes(client):
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    client.post("/vessels", json={"name": "MV Test"}, headers={"X-User": "Captain Ahab"})
    incident = client.post(
        "/vessels/MV Test/safety",
        json={"incident_type": "near_miss", "description": "Loose grating"},
    ).json()
    # No JSON body at all — this used to 422 (missing field) instead of running
    # the role check, since all of CloseIncidentIn's fields are optional and
    # FastAPI still required *a* body before the fix.
    resp = client.post(f"/safety/{incident['id']}/close", headers={"X-User": "Captain Ahab"})
    assert resp.status_code == 200


def test_crew_expiring_certs(client):
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    client.post("/vessels", json={"name": "MV Test"}, headers={"X-User": "Captain Ahab"})
    soon = (date.today() + timedelta(days=10)).isoformat()
    far = (date.today() + timedelta(days=90)).isoformat()
    client.post(
        "/crew",
        json={
            "name": "Jane Doe",
            "rank": "Chief Officer",
            "vessel": "MV Test",
            "stcw_cert_expiry": soon,
        },
        headers={"X-User": "Captain Ahab"},
    )
    client.post(
        "/crew",
        json={
            "name": "John Roe",
            "rank": "Second Officer",
            "vessel": "MV Test",
            "stcw_cert_expiry": far,
        },
        headers={"X-User": "Captain Ahab"},
    )

    resp = client.get("/crew/expiring-certs")
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert names == ["Jane Doe"]


def test_safety_reportable(client):
    client.post("/users", json={"name": "Captain Ahab", "role": "master"})
    client.post("/vessels", json={"name": "MV Test"}, headers={"X-User": "Captain Ahab"})
    client.post(
        "/vessels/MV Test/safety",
        json={
            "incident_type": "incident",
            "description": "Total loss of steering",
            "severity": "critical",
        },
    )
    client.post(
        "/vessels/MV Test/safety",
        json={"incident_type": "near_miss", "description": "Loose grating", "severity": "low"},
    )

    resp = client.get("/safety/reportable")
    assert resp.status_code == 200
    descriptions = [i["description"] for i in resp.json()]
    assert descriptions == ["Total loss of steering"]
