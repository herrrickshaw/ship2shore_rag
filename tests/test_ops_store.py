import os
import tempfile

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
    cid = sqlite_store.add_crew("Jane Doe", "Chief Officer", vessel_id=vid, sign_on_date="2026-01-01")
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
