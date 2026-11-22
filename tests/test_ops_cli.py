"""End-to-end tests of the operations sub-commands, driven through the real
argparse tree (cli.main) against a throwaway SQLite ops database."""

from datetime import date, timedelta

import pytest

import cli
from ops import store


@pytest.fixture
def ops(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(store, "STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(store, "OPS_SQLITE_PATH", str(tmp_path / "ops.sqlite3"))
    monkeypatch.delenv("SHIP2SHORE_USER", raising=False)

    def run(*argv):
        monkeypatch.setattr("sys.argv", ["cli.py", *argv])
        capsys.readouterr()  # drop output from earlier calls
        cli.main()
        return capsys.readouterr().out

    return run


@pytest.fixture
def fleet(ops):
    """A master, a vessel and an engine on it."""
    ops("user", "add", "alice", "--role", "master", "--email", "a@x.io")
    ops("vessel", "add", "MV Tester", "--imo", "9999999", "--user", "alice")
    return ops


def lines(out):
    return out.strip().splitlines()


# ---- users ----------------------------------------------------------------


def test_user_add_and_list(ops):
    out = ops("user", "add", "alice", "--role", "master", "--email", "a@x.io")
    assert lines(out) == ["added user #1: alice (master)"]
    ops("user", "add", "bob", "--role", "deck_crew")
    out = lines(ops("user", "list"))
    assert len(out) == 2
    assert out[0].startswith("#1  alice")
    assert "master" in out[0] and out[0].rstrip().endswith("a@x.io")
    assert out[1].startswith("#2  bob")
    assert out[1].rstrip().endswith("deck_crew")  # no email -> blank, not "None"


def test_user_add_rejects_unknown_role(ops):
    with pytest.raises(SystemExit):
        ops("user", "add", "eve", "--role", "pirate")


# ---- vessels / authorization ---------------------------------------------


def test_vessel_add_requires_a_privileged_user(ops):
    ops("user", "add", "bob", "--role", "deck_crew")
    with pytest.raises(SystemExit) as e:
        ops("vessel", "add", "MV X")
    assert "permission denied" in str(e.value)
    with pytest.raises(SystemExit) as e:
        ops("vessel", "add", "MV X", "--user", "bob")
    assert "deck_crew" in str(e.value)
    assert store.list_vessels() == []


def test_user_from_environment(ops, monkeypatch):
    ops("user", "add", "alice", "--role", "master")
    monkeypatch.setenv("SHIP2SHORE_USER", "alice")
    assert lines(ops("vessel", "add", "MV Env")) == ["added vessel #1: MV Env"]


def test_unknown_user_name_is_denied(ops):
    with pytest.raises(SystemExit) as e:
        ops("vessel", "add", "MV X", "--user", "ghost")
    assert "permission denied" in str(e.value)


def test_vessel_add_stores_only_given_fields_and_lists(ops):
    ops("user", "add", "alice", "--role", "master")
    out = ops(
        "vessel", "add", "MV Full", "--imo", "1234567", "--flag", "PA", "--type", "tanker",
        "--gt", "5000.5", "--dwt", "9000", "--build-year", "2010", "--class-society", "DNV",
        "--main-engine", "MAN B&W", "--user", "alice",
    )  # fmt: skip
    assert out.strip() == "added vessel #1: MV Full"
    v = store.get_vessel("1234567")
    assert (v["flag"], v["vessel_type"], v["gross_tonnage"], v["deadweight"]) == (
        "PA", "tanker", 5000.5, 9000.0,
    )  # fmt: skip
    assert (v["build_year"], v["classification_society"], v["main_engine"]) == (
        2010, "DNV", "MAN B&W",
    )  # fmt: skip
    ops("vessel", "add", "MV Bare", "--user", "alice")
    out = lines(ops("vessel", "list"))
    full = next(x for x in out if "MV Full" in x)
    bare = next(x for x in out if "MV Bare" in x)
    assert "IMO 1234567" in full and full.rstrip().endswith("tanker")
    assert "IMO -" in bare  # missing IMO renders as a dash


def test_unknown_vessel_exits_with_hint(fleet):
    with pytest.raises(SystemExit) as e:
        fleet("log", "list", "MV Nope")
    assert "no vessel matching 'MV Nope'" in str(e.value)
    assert "vessel add" in str(e.value)


# ---- crew -------------------------------------------------------------------


def test_crew_add_list_signoff(fleet):
    out = fleet(
        "crew", "add", "Jane Doe", "Chief Officer", "--vessel", "9999999", "--nationality", "IN",
        "--stcw-number", "C1", "--stcw-expiry", "2030-01-01", "--sign-on", "2026-01-01",
        "--user", "alice",
    )  # fmt: skip
    assert out.strip() == "added crew #1: Jane Doe (Chief Officer) on MV Tester"
    out = lines(fleet("crew", "list"))
    assert out[0].endswith("aboard") and "Jane Doe" in out[0]
    assert lines(fleet("crew", "list", "--vessel", "MV Tester"))[0].endswith("aboard")
    assert fleet("crew", "signoff", "1", "--date", "2026-06-01", "--user", "alice").strip() == (
        "crew #1 signed off 2026-06-01"
    )
    assert lines(fleet("crew", "list"))[0].endswith("signed off 2026-06-01")


def test_crew_list_filters_by_vessel(fleet):
    fleet("vessel", "add", "MV Other", "--user", "alice")
    fleet("crew", "add", "A", "Cook", "--vessel", "MV Tester", "--user", "alice")
    fleet("crew", "add", "B", "Cook", "--vessel", "MV Other", "--user", "alice")
    out = lines(fleet("crew", "list", "--vessel", "MV Other"))
    assert len(out) == 1 and " B " in out[0]


def test_crew_signon_and_signoff_are_restricted(fleet):
    fleet("user", "add", "dan", "--role", "deck_crew")
    with pytest.raises(SystemExit):
        fleet("crew", "add", "A", "Cook", "--vessel", "MV Tester", "--user", "dan")
    with pytest.raises(SystemExit):
        fleet("crew", "signoff", "1", "--date", "2026-01-01", "--user", "dan")


def test_expiring_certs_window_and_empty_message(fleet):
    out = fleet("crew", "expiring-certs")
    assert out.strip() == "no STCW certificates expiring within 30 days"
    soon = (date.today() + timedelta(days=10)).isoformat()
    later = (date.today() + timedelta(days=100)).isoformat()
    fleet("crew", "add", "Soon", "Cook", "--vessel", "MV Tester", "--stcw-expiry", soon,
          "--user", "alice")  # fmt: skip
    fleet("crew", "add", "Later", "Cook", "--vessel", "MV Tester", "--stcw-expiry", later,
          "--user", "alice")  # fmt: skip
    out = lines(fleet("crew", "expiring-certs"))
    assert len(out) == 1 and "Soon" in out[0] and f"expires {soon}" in out[0]
    assert "MV Tester" in out[0]
    both = lines(fleet("crew", "expiring-certs", "--days", "200"))
    assert len(both) == 2
    assert fleet("crew", "expiring-certs", "--days", "5").strip() == (
        "no STCW certificates expiring within 5 days"
    )


# ---- logs -------------------------------------------------------------------


def test_log_add_list_and_role_gate(fleet):
    out = fleet("log", "add", "MV Tester", "captain", "All well", "--lat", "1.5", "--lon", "2.5",
                "--user", "alice")  # fmt: skip
    assert out.strip() == "added captain log entry #1 on MV Tester"
    fleet("user", "add", "dan", "--role", "deck_crew")
    fleet("log", "add", "MV Tester", "deck", "Watch handed over", "--user", "dan")
    with pytest.raises(SystemExit):
        fleet("log", "add", "MV Tester", "captain", "Mutiny", "--user", "dan")
    with pytest.raises(SystemExit):  # engine log not open to deck crew
        fleet("log", "add", "MV Tester", "engine", "x", "--user", "dan")
    rows = store.list_log_entries(1)
    cap = next(r for r in rows if r["log_type"] == "captain")
    assert (cap["latitude"], cap["longitude"]) == (1.5, 2.5)
    assert cap["logged_by"] == 1
    out = lines(fleet("log", "list", "MV Tester"))
    assert len(out) == 2
    only = lines(fleet("log", "list", "MV Tester", "--type", "deck"))
    assert len(only) == 1 and "[deck]  Watch handed over" in only[0]


# ---- equipment / parts / maintenance ------------------------------------------


def test_equipment_parts_maintenance_flow(fleet):
    fleet("user", "add", "chief", "--role", "chief_engineer")
    out = fleet(
        "equipment", "add", "MV Tester", "Main Engine", "--type", "diesel", "--manufacturer", "MAN",
        "--model", "6S60", "--serial", "SN1", "--user", "chief",
    )  # fmt: skip
    assert out.strip() == "added equipment #1: Main Engine on MV Tester"
    assert "Main Engine" in fleet("equipment", "list", "MV Tester")
    assert "MAN 6S60" in fleet("equipment", "list", "MV Tester")

    out = fleet("parts", "add", "1", "PN-1", "Liner", "--manufacturer", "MAN", "--qty", "4",
                "--user", "chief")  # fmt: skip
    assert out.strip() == "added part #1: PN-1 — Liner"
    assert lines(fleet("parts", "list", "1"))[0].endswith("qty 4")

    out = fleet("maintenance", "add", "1", "breakdown", "Cracked liner", "--hours", "1234.5",
                "--parts-used", "PN-1 x1", "--user", "chief")  # fmt: skip
    assert out.strip() == "added maintenance job #1: breakdown — Cracked liner"
    m = store.list_maintenance(1)[0]
    assert (m["running_hours"], m["parts_used"]) == (1234.5, "PN-1 x1")
    assert m["performed_by"] == 2  # chief is the 2nd registered user
    assert "[breakdown]  Cracked liner" in fleet("maintenance", "list", "1")


def test_equipment_and_parts_denied_for_deck_crew(fleet):
    fleet("user", "add", "dan", "--role", "deck_crew")
    for argv in (
        ("equipment", "add", "MV Tester", "Crane", "--user", "dan"),
        ("parts", "add", "1", "P", "N", "--user", "dan"),
        ("maintenance", "add", "1", "repair", "x", "--user", "dan"),
        ("fuel", "add", "MV Tester", "MGO", "bunkering", "5", "--user", "dan"),
    ):
        with pytest.raises(SystemExit):
            fleet(*argv)


# ---- fuel -------------------------------------------------------------------


def test_fuel_add_and_list(fleet):
    out = fleet("fuel", "add", "MV Tester", "VLSFO", "bunkering", "250.5", "--rob", "300",
                "--location", "Fujairah", "--user", "alice")  # fmt: skip
    assert out.strip() == "added fuel log #1: bunkering 250.5mt VLSFO"
    fleet("fuel", "add", "MV Tester", "VLSFO", "consumption", "20", "--user", "alice")
    out = lines(fleet("fuel", "list", "MV Tester"))
    assert len(out) == 2
    joined = "\n".join(out)
    assert "ROB 300.0" in joined and "ROB -" in joined


# ---- procurement ------------------------------------------------------------


def test_procurement_lifecycle(fleet):
    out = fleet(
        "procurement", "add", "MV Tester", "PN-1 liner x2", "--supplier", "Acme", "--cost", "1500",
        "--currency", "USD", "--expected-delivery", "2026-12-01", "--user", "alice",
    )  # fmt: skip
    assert out.strip() == "added purchase order #1 for MV Tester: PN-1 liner x2 (status: requested)"
    out = lines(fleet("procurement", "list", "MV Tester"))
    assert "[requested]" in out[0] and "supplier=Acme" in out[0] and "cost=1500.0" in out[0]
    assert store.list_purchase_orders(1)[0]["requested_by"] == 1
    assert fleet("procurement", "approve", "1", "--user", "alice").strip() == (
        "purchase order #1 approved"
    )
    assert store.list_purchase_orders(1)[0]["approved_by"] == 1
    assert lines(fleet("procurement", "list", "MV Tester", "--status", "approved"))
    assert fleet("procurement", "list", "MV Tester", "--status", "requested").strip() == ""
    out = fleet("procurement", "status", "1", "received", "--user", "alice")
    assert out.strip() == "purchase order #1 status set to received"
    assert "[received]" in fleet("procurement", "list", "MV Tester")


def test_procurement_bare_order_shows_dashes_and_gates(fleet):
    fleet("user", "add", "dan", "--role", "deck_crew")
    fleet("procurement", "add", "MV Tester", "rope", "--user", "alice")
    assert "supplier=-  cost=-" in fleet("procurement", "list", "MV Tester")
    with pytest.raises(SystemExit):
        fleet("procurement", "add", "MV Tester", "rope", "--user", "dan")
    with pytest.raises(SystemExit):
        fleet("procurement", "approve", "1", "--user", "dan")
    with pytest.raises(SystemExit):
        fleet("procurement", "status", "1", "ordered", "--user", "dan")


# ---- drydock ----------------------------------------------------------------


def test_drydock_add_and_list(fleet):
    out = fleet(
        "drydock", "add", "MV Tester", "--yard", "Dubai Drydocks", "--location", "Dubai",
        "--start", "2027-01-10", "--end", "2027-02-10", "--scope", "Hull paint", "--cost", "9e5",
        "--currency", "USD", "--user", "alice",
    )  # fmt: skip
    assert out.strip() == "added drydock event #1 for MV Tester"
    line = lines(fleet("drydock", "list", "MV Tester"))[0]
    assert "[planned]" in line and "Dubai Drydocks" in line
    assert "2027-01-10 to 2027-02-10" in line
    fleet("drydock", "add", "MV Tester", "--user", "alice")
    assert "-  - to -" in fleet("drydock", "list", "MV Tester")
    assert {d["coordinated_by"] for d in store.list_drydock_events(1)} == {1}


def test_drydock_requires_privileged_user(fleet):
    fleet("user", "add", "dan", "--role", "deck_crew")
    with pytest.raises(SystemExit):
        fleet("drydock", "add", "MV Tester", "--user", "dan")


# ---- safety -----------------------------------------------------------------


def test_safety_report_is_unrestricted_and_lists(fleet):
    fleet("user", "add", "dan", "--role", "deck_crew")
    out = fleet("safety", "report", "MV Tester", "near_miss", "Slipped on deck", "--user", "dan")
    assert out.strip() == "reported near_miss #1 on MV Tester (status: open)"
    fleet("safety", "report", "MV Tester", "incident", "Fire", "--severity", "critical")
    all_lines = lines(fleet("safety", "list", "MV Tester"))
    assert len(all_lines) == 2
    by_desc = {i["description"]: i for i in store.list_safety_incidents(1)}
    assert by_desc["Slipped on deck"]["reported_by"] == 2  # dan
    assert by_desc["Fire"]["reported_by"] is None  # anonymous report
    assert lines(fleet("safety", "list", "MV Tester", "--status", "closed")) == []
    assert "Slipped on deck" in fleet("safety", "list", "MV Tester", "--status", "open")


def test_safety_report_find_similar_prints_hits(fleet, monkeypatch):
    import rag.similar_incidents as si

    seen = {}

    def fake_find(description):
        seen["d"] = description
        return [{"title": "MAIB A", "url": "http://x/a", "score": 0.123456}]

    monkeypatch.setattr(si, "find_similar_incidents", fake_find)
    out = fleet("safety", "report", "MV Tester", "incident", "Engine fire", "--find-similar")
    assert seen["d"] == "Engine fire"
    assert "Similar past incidents in the ingested corpus:" in out
    assert "[1] MAIB A (http://x/a) — score 0.1235" in out


def test_safety_report_find_similar_empty_prints_no_section(fleet, monkeypatch):
    import rag.similar_incidents as si

    monkeypatch.setattr(si, "find_similar_incidents", lambda d: [])
    out = fleet("safety", "report", "MV Tester", "incident", "Engine fire", "--find-similar")
    assert "Similar past incidents" not in out


def test_safety_report_without_flag_does_not_search(fleet, monkeypatch):
    import rag.similar_incidents as si

    def boom(_):
        raise AssertionError("must not be called")

    monkeypatch.setattr(si, "find_similar_incidents", boom)
    fleet("safety", "report", "MV Tester", "audit", "Annual audit")


def test_safety_reportable_and_close(fleet):
    assert fleet("safety", "reportable").strip() == (
        "no open critical incidents requiring a flag-State casualty report"
    )
    fleet("safety", "report", "MV Tester", "incident", "Grounding", "--severity", "critical")
    fleet("safety", "report", "MV Tester", "incident", "Scratch", "--severity", "low")
    out = lines(fleet("safety", "reportable"))
    assert len(out) == 1 and "Grounding" in out[0] and "MV Tester" in out[0]
    fleet("user", "add", "dan", "--role", "deck_crew")
    with pytest.raises(SystemExit):
        fleet("safety", "close", "1", "--user", "dan")
    out = fleet("safety", "close", "1", "--corrective-action", "Re-survey", "--user", "alice")
    assert out.strip() == "safety incident #1 closed"
    inc = store.list_safety_incidents(1, status="closed")[0]
    assert inc["corrective_action"] == "Re-survey" and inc["closed_by"] == 1
    assert "no open critical" in fleet("safety", "reportable")


# ---- fleet ------------------------------------------------------------------


def test_fleet_status_empty(ops):
    out = lines(ops("fleet", "status"))
    assert out == [
        "Fleet: 0 vessel(s)",
        "Open safety incidents: 0",
        "STCW certs expiring within 30d: 0",
        "Drydocks starting within 90d: 0",
    ]


def test_fleet_status_populated_and_windows(fleet):
    soon = (date.today() + timedelta(days=5)).isoformat()
    fleet("crew", "add", "Jane", "Master", "--vessel", "MV Tester", "--stcw-expiry", soon,
          "--user", "alice")  # fmt: skip
    fleet("safety", "report", "MV Tester", "audit", "Audit")
    fleet("safety", "report", "MV Tester", "incident", "Fire", "--severity", "high")
    fleet("safety", "report", "MV Tester", "incident", "Smoke", "--severity", "high")
    start = (date.today() + timedelta(days=45)).isoformat()
    fleet("drydock", "add", "MV Tester", "--yard", "Yard1", "--start", start, "--user", "alice")
    out = fleet("fleet", "status")
    assert "Fleet: 1 vessel(s)" in out
    assert "Open safety incidents: 3" in out
    assert "  high: 2" in out and "  unspecified: 1" in out
    assert out.index("  high: 2") < out.index("  unspecified: 1")  # sorted by severity name
    assert "STCW certs expiring within 30d: 1" in out
    assert f"  Jane (Master) on MV Tester — expires {soon}" in out
    assert "Drydocks starting within 90d: 1" in out
    assert f"  MV Tester — Yard1 starting {start}" in out
    narrow = fleet("fleet", "status", "--cert-days", "1", "--drydock-days", "10")
    assert "STCW certs expiring within 1d: 0" in narrow
    assert "Drydocks starting within 10d: 0" in narrow
