import os
import tempfile
from datetime import date, timedelta

import pytest

sqlite3 = pytest.importorskip("sqlite3")


@pytest.fixture
def sqlite_store(monkeypatch):
    """ops.store against a throwaway SQLite file — no Postgres needed."""
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.remove(path)

    from ops import store

    monkeypatch.setattr(store, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(store, "OPS_SQLITE_PATH", path)
    yield store
    if os.path.exists(path):
        os.remove(path)


def test_list_all_open_incidents_spans_every_severity(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    open_critical = sqlite_store.add_safety_incident(
        vid, "incident", "Engine room fire", severity="critical"
    )
    open_low = sqlite_store.add_safety_incident(vid, "near_miss", "Loose grating", severity="low")
    closed = sqlite_store.add_safety_incident(vid, "incident", "Minor spill", severity="medium")
    sqlite_store.close_safety_incident(closed, closed_by=None)

    open_ids = {i["id"] for i in sqlite_store.list_all_open_incidents()}
    assert open_ids == {open_critical, open_low}


def test_list_upcoming_drydocks_filters_by_window_and_status(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    today = date.today()
    soon = sqlite_store.add_drydock_event(
        vid, yard="Keppel", planned_start=str(today + timedelta(days=30)), status="planned"
    )
    sqlite_store.add_drydock_event(
        vid, yard="Later Yard", planned_start=str(today + timedelta(days=300)), status="planned"
    )
    sqlite_store.add_drydock_event(
        vid, yard="Done Yard", planned_start=str(today - timedelta(days=10)), status="completed"
    )

    upcoming = sqlite_store.list_upcoming_drydocks(days_ahead=90)
    assert [d["id"] for d in upcoming] == [soon]
    assert upcoming[0]["vessel_name"] == "MV Tester"


def test_fleet_status_aggregates_across_vessels(sqlite_store):
    v1 = sqlite_store.add_vessel("MV One")
    v2 = sqlite_store.add_vessel("MV Two")
    sqlite_store.add_safety_incident(v1, "incident", "Fire", severity="critical")
    sqlite_store.add_safety_incident(v2, "near_miss", "Slip", severity="low")
    today = date.today()
    sqlite_store.add_crew(
        "Jane Doe",
        "Chief Officer",
        vessel_id=v1,
        stcw_cert_expiry=str(today + timedelta(days=5)),
    )
    sqlite_store.add_drydock_event(
        v2, yard="Keppel", planned_start=str(today + timedelta(days=10)), status="planned"
    )

    status = sqlite_store.fleet_status()

    assert status["vessel_count"] == 2
    assert len(status["open_incidents"]) == 2
    assert status["open_incidents_by_severity"] == {"critical": 1, "low": 1}
    assert len(status["certs_expiring"]) == 1
    assert len(status["drydocks_upcoming"]) == 1


def test_fleet_status_with_no_data(sqlite_store):
    status = sqlite_store.fleet_status()
    assert status == {
        "vessel_count": 0,
        "open_incidents": [],
        "open_incidents_by_severity": {},
        "certs_expiring": [],
        "drydocks_upcoming": [],
    }
