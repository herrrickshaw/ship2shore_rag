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


def test_vessel_roundtrip(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester", imo_number="1234567", vessel_type="bulk carrier")
    vessels = sqlite_store.list_vessels()
    assert len(vessels) == 1
    assert vessels[0]["name"] == "MV Tester"
    assert sqlite_store.get_vessel("1234567")["id"] == vid
    assert sqlite_store.get_vessel("MV Tester")["id"] == vid


def test_crew_signon_and_signoff(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    cid = sqlite_store.add_crew(
        "Jane Doe", "Chief Officer", vessel_id=vid, sign_on_date="2026-01-01"
    )
    crew = sqlite_store.list_crew(vessel_id=vid)
    assert crew[0]["sign_off_date"] is None

    sqlite_store.crew_signoff(cid, "2026-06-01")
    crew = sqlite_store.list_crew(vessel_id=vid)
    assert crew[0]["sign_off_date"] == "2026-06-01"


def test_log_entry_and_type_filter(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    sqlite_store.add_log_entry(vid, "deck", "Routine watch.")
    sqlite_store.add_log_entry(vid, "captain", "Departed port.")

    all_entries = sqlite_store.list_log_entries(vid)
    assert len(all_entries) == 2
    deck_only = sqlite_store.list_log_entries(vid, log_type="deck")
    assert len(deck_only) == 1
    assert deck_only[0]["entry_text"] == "Routine watch."


def test_equipment_parts_maintenance_chain(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    eid = sqlite_store.add_equipment(vid, "Main Engine", manufacturer="MAN B&W")
    sqlite_store.add_part(eid, "PN-1", "Fuel injector", stock_quantity=3)
    sqlite_store.add_maintenance(eid, "scheduled", "Injector service", running_hours=10000)

    assert sqlite_store.list_equipment(vid)[0]["manufacturer"] == "MAN B&W"
    assert sqlite_store.list_parts(eid)[0]["part_number"] == "PN-1"
    assert sqlite_store.list_maintenance(eid)[0]["description"] == "Injector service"


def test_fuel_log(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    sqlite_store.add_fuel_entry(vid, "VLSFO", "bunkering", 500.0, rob_after_mt=1200.0)
    entries = sqlite_store.list_fuel_log(vid)
    assert entries[0]["quantity_mt"] == 500.0
    assert entries[0]["event_type"] == "bunkering"


def test_purchase_order_approval_workflow(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    po_id = sqlite_store.add_purchase_order(vid, "PN-1 Fuel injector x2", supplier="MAN")
    assert sqlite_store.list_purchase_orders(vid)[0]["status"] == "requested"

    sqlite_store.approve_purchase_order(po_id, approved_by=None)
    assert sqlite_store.list_purchase_orders(vid)[0]["status"] == "approved"

    sqlite_store.update_purchase_order_status(po_id, "received")
    orders = sqlite_store.list_purchase_orders(vid, status="received")
    assert len(orders) == 1
    assert orders[0]["id"] == po_id


def test_drydock_event(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    sqlite_store.add_drydock_event(vid, yard="Keppel Shipyard", planned_start="2027-03-01")
    events = sqlite_store.list_drydock_events(vid)
    assert events[0]["yard"] == "Keppel Shipyard"
    assert events[0]["status"] == "planned"


def test_safety_incident_report_and_close(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    incident_id = sqlite_store.add_safety_incident(
        vid, "near_miss", "Loose grating", severity="medium"
    )
    open_incidents = sqlite_store.list_safety_incidents(vid, status="open")
    assert len(open_incidents) == 1

    sqlite_store.close_safety_incident(
        incident_id, closed_by=None, corrective_action="Grating re-secured"
    )
    closed = sqlite_store.list_safety_incidents(vid, status="closed")
    assert closed[0]["corrective_action"] == "Grating re-secured"


def test_list_expiring_certs(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    today = date.today()
    soon = sqlite_store.add_crew(
        "Jane Doe",
        "Chief Officer",
        vessel_id=vid,
        stcw_cert_expiry=str(today + timedelta(days=10)),
    )
    sqlite_store.add_crew(
        "John Roe",
        "Second Officer",
        vessel_id=vid,
        stcw_cert_expiry=str(today + timedelta(days=90)),
    )
    signed_off = sqlite_store.add_crew(
        "Off Duty",
        "Third Officer",
        vessel_id=vid,
        stcw_cert_expiry=str(today + timedelta(days=1)),
    )
    sqlite_store.crew_signoff(signed_off, str(today))
    sqlite_store.add_crew("No Cert", "Deck Crew", vessel_id=vid)

    expiring = sqlite_store.list_expiring_certs(days_ahead=30)
    assert [c["id"] for c in expiring] == [soon]
    assert expiring[0]["vessel_name"] == "MV Tester"

    assert sqlite_store.list_expiring_certs(days_ahead=5) == []


def test_list_reportable_incidents(sqlite_store):
    vid = sqlite_store.add_vessel("MV Tester")
    critical_open = sqlite_store.add_safety_incident(
        vid, "incident", "Total loss of steering", severity="critical"
    )
    critical_closed = sqlite_store.add_safety_incident(
        vid, "incident", "Engine room fire, contained", severity="critical"
    )
    sqlite_store.close_safety_incident(critical_closed, closed_by=None)
    sqlite_store.add_safety_incident(vid, "near_miss", "Loose grating", severity="low")

    reportable = sqlite_store.list_reportable_incidents()
    assert [i["id"] for i in reportable] == [critical_open]
    assert reportable[0]["vessel_name"] == "MV Tester"
