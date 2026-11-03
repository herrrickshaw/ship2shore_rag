"""argparse wiring for the operations subcommands, one registrar per domain.

Handlers live in `ops_cli`; they are looked up on the module passed to
`register_all`, so this file only describes flags and never imports it.
"""


def _add_user_flag(parser):
    parser.add_argument("--user", default=None, help="acting user's name (or set SHIP2SHORE_USER)")


def _register_user(sub, h) -> None:
    p = sub.add_parser(
        "user",
        help="IAM — register users and their role (master/chief_engineer/officer/deck_crew/engine_crew/shore_staff)",
    )
    user_sub = p.add_subparsers(dest="user_command", required=True)
    p_add = user_sub.add_parser("add", help="register a user")
    p_add.add_argument("name")
    p_add.add_argument(
        "--role",
        required=True,
        choices=["master", "chief_engineer", "officer", "deck_crew", "engine_crew", "shore_staff"],
    )
    p_add.add_argument("--email", default=None)
    p_add.set_defaults(func=h.cmd_user_add)
    user_sub.add_parser("list", help="list registered users").set_defaults(func=h.cmd_user_list)


def _register_vessel(sub, h) -> None:
    p = sub.add_parser(
        "vessel", help="ship specifics — IMO number, flag, type, tonnage, main engine"
    )
    vessel_sub = p.add_subparsers(dest="vessel_command", required=True)
    p_add = vessel_sub.add_parser("add", help="register a vessel")
    p_add.add_argument("name")
    p_add.add_argument("--imo", default=None, help="IMO number")
    p_add.add_argument("--flag", default=None)
    p_add.add_argument("--type", default=None, help="e.g. bulk carrier, container ship, tanker")
    p_add.add_argument("--gt", type=float, default=None, help="gross tonnage")
    p_add.add_argument("--dwt", type=float, default=None, help="deadweight tonnage")
    p_add.add_argument("--build-year", type=int, default=None)
    p_add.add_argument("--class-society", default=None, help="e.g. DNV, ABS, Lloyd's Register")
    p_add.add_argument("--main-engine", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_vessel_add)
    vessel_sub.add_parser("list", help="list registered vessels").set_defaults(
        func=h.cmd_vessel_list
    )


def _register_crew(sub, h) -> None:
    p = sub.add_parser(
        "crew", help="seafarer onboarding — rank, nationality, STCW certification, sign-on/off"
    )
    crew_sub = p.add_subparsers(dest="crew_command", required=True)
    p_add = crew_sub.add_parser("add", help="sign a crew member on to a vessel")
    p_add.add_argument("name")
    p_add.add_argument("rank")
    p_add.add_argument("--vessel", required=True, help="vessel name or IMO number")
    p_add.add_argument("--nationality", default=None)
    p_add.add_argument("--stcw-number", default=None, help="STCW certificate number")
    p_add.add_argument(
        "--stcw-expiry", default=None, help="STCW certificate expiry date (YYYY-MM-DD)"
    )
    p_add.add_argument("--sign-on", default=None, help="sign-on date (YYYY-MM-DD)")
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_crew_add)
    p_list = crew_sub.add_parser("list", help="list crew, optionally filtered to one vessel")
    p_list.add_argument("--vessel", default=None)
    p_list.set_defaults(func=h.cmd_crew_list)
    p_signoff = crew_sub.add_parser("signoff", help="sign a crew member off")
    p_signoff.add_argument("crew_id", type=int)
    p_signoff.add_argument("--date", required=True, help="sign-off date (YYYY-MM-DD)")
    _add_user_flag(p_signoff)
    p_signoff.set_defaults(func=h.cmd_crew_signoff)
    p_expiring = crew_sub.add_parser(
        "expiring-certs",
        help="list currently-aboard crew whose STCW certificate has expired or is expiring soon",
    )
    p_expiring.add_argument(
        "--days", type=int, default=30, help="look-ahead window in days (default: 30)"
    )
    p_expiring.set_defaults(func=h.cmd_crew_expiring_certs)


def _register_log(sub, h) -> None:
    p = sub.add_parser("log", help="master/captain's, deck, and engine logbook entries")
    log_sub = p.add_subparsers(dest="log_command", required=True)
    p_add = log_sub.add_parser(
        "add", help="add a log entry (captain's-log entries require the master role)"
    )
    p_add.add_argument("vessel", help="vessel name or IMO number")
    p_add.add_argument("log_type", choices=["deck", "engine", "captain"])
    p_add.add_argument("text")
    p_add.add_argument("--lat", type=float, default=None)
    p_add.add_argument("--lon", type=float, default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_log_add)
    p_list = log_sub.add_parser("list", help="list a vessel's log entries, newest first")
    p_list.add_argument("vessel")
    p_list.add_argument("--type", default=None, choices=["deck", "engine", "captain"])
    p_list.set_defaults(func=h.cmd_log_list)


def _register_equipment(sub, h) -> None:
    p = sub.add_parser(
        "equipment", help="engineering asset registry (main engine, generators, etc.) per vessel"
    )
    eq_sub = p.add_subparsers(dest="equipment_command", required=True)
    p_add = eq_sub.add_parser("add", help="register a piece of equipment on a vessel")
    p_add.add_argument("vessel")
    p_add.add_argument("name")
    p_add.add_argument("--type", default=None, help="e.g. diesel engine, generator, pump")
    p_add.add_argument("--manufacturer", default=None)
    p_add.add_argument("--model", default=None)
    p_add.add_argument("--serial", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_equipment_add)
    p_list = eq_sub.add_parser("list", help="list a vessel's equipment")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=h.cmd_equipment_list)


def _register_parts(sub, h) -> None:
    p = sub.add_parser("parts", help="EPC — electronic parts catalog")
    parts_sub = p.add_subparsers(dest="parts_command", required=True)
    p_add = parts_sub.add_parser("add", help="add a spare part to an equipment's catalog entry")
    p_add.add_argument("equipment_id", type=int)
    p_add.add_argument("part_number")
    p_add.add_argument("part_name")
    p_add.add_argument("--manufacturer", default=None)
    p_add.add_argument("--qty", type=int, default=None, help="stock quantity")
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_parts_add)
    p_list = parts_sub.add_parser("list", help="list an equipment's spare parts")
    p_list.add_argument("equipment_id", type=int)
    p_list.set_defaults(func=h.cmd_parts_list)


def _register_maintenance(sub, h) -> None:
    p = sub.add_parser(
        "maintenance", help="repair/maintenance job history for a piece of equipment"
    )
    maint_sub = p.add_subparsers(dest="maintenance_command", required=True)
    p_add = maint_sub.add_parser("add", help="log a maintenance/repair job")
    p_add.add_argument("equipment_id", type=int)
    p_add.add_argument("job_type", choices=["scheduled", "breakdown", "repair", "inspection"])
    p_add.add_argument("description")
    p_add.add_argument("--hours", type=float, default=None, help="running hours at time of job")
    p_add.add_argument("--parts-used", default=None, help='free text, e.g. "PN-9001 x1"')
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_maintenance_add)
    p_list = maint_sub.add_parser(
        "list", help="list an equipment's maintenance history, newest first"
    )
    p_list.add_argument("equipment_id", type=int)
    p_list.set_defaults(func=h.cmd_maintenance_list)


def _register_fuel(sub, h) -> None:
    p = sub.add_parser("fuel", help="bunkering/consumption/ROB log for a vessel")
    fuel_sub = p.add_subparsers(dest="fuel_command", required=True)
    p_add = fuel_sub.add_parser("add", help="log a fuel event")
    p_add.add_argument("vessel")
    p_add.add_argument("fuel_type", help="e.g. VLSFO, MGO, LSMGO")
    p_add.add_argument("event_type", choices=["bunkering", "consumption", "ROB"])
    p_add.add_argument("quantity_mt", type=float)
    p_add.add_argument(
        "--rob", type=float, default=None, help="remaining on board after this event, in mt"
    )
    p_add.add_argument("--location", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_fuel_add)
    p_list = fuel_sub.add_parser("list", help="list a vessel's fuel log, newest first")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=h.cmd_fuel_list)


def _register_procurement(sub, h) -> None:
    p = sub.add_parser("procurement", help="purchase-to-pay — orders tied to the EPC parts catalog")
    proc_sub = p.add_subparsers(dest="procurement_command", required=True)
    p_add = proc_sub.add_parser("add", help="request a purchase order")
    p_add.add_argument("vessel")
    p_add.add_argument("items", help='free text, e.g. "PN-9001 Cylinder liner x2"')
    p_add.add_argument("--equipment-id", type=int, default=None)
    p_add.add_argument("--supplier", default=None)
    p_add.add_argument("--cost", type=float, default=None, help="total cost")
    p_add.add_argument("--currency", default=None)
    p_add.add_argument("--expected-delivery", default=None, help="YYYY-MM-DD")
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_procurement_add)
    p_list = proc_sub.add_parser("list", help="list a vessel's purchase orders")
    p_list.add_argument("vessel")
    p_list.add_argument(
        "--status",
        default=None,
        choices=["requested", "approved", "ordered", "received", "cancelled"],
    )
    p_list.set_defaults(func=h.cmd_procurement_list)
    p_approve = proc_sub.add_parser("approve", help="approve a requested purchase order")
    p_approve.add_argument("po_id", type=int)
    _add_user_flag(p_approve)
    p_approve.set_defaults(func=h.cmd_procurement_approve)
    p_status = proc_sub.add_parser(
        "status", help="update a purchase order's status (e.g. ordered, received)"
    )
    p_status.add_argument("po_id", type=int)
    p_status.add_argument(
        "status", choices=["requested", "approved", "ordered", "received", "cancelled"]
    )
    _add_user_flag(p_status)
    p_status.set_defaults(func=h.cmd_procurement_status)


def _register_drydock(sub, h) -> None:
    p = sub.add_parser("drydock", help="dry-docking events — scheduling, yard, cost")
    dd_sub = p.add_subparsers(dest="drydock_command", required=True)
    p_add = dd_sub.add_parser("add", help="schedule a dry-docking event")
    p_add.add_argument("vessel")
    p_add.add_argument("--yard", default=None)
    p_add.add_argument("--location", default=None)
    p_add.add_argument("--start", default=None, help="planned start date (YYYY-MM-DD)")
    p_add.add_argument("--end", default=None, help="planned end date (YYYY-MM-DD)")
    p_add.add_argument("--scope", default=None, help="scope of work description")
    p_add.add_argument("--cost", type=float, default=None)
    p_add.add_argument("--currency", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=h.cmd_drydock_add)
    p_list = dd_sub.add_parser("list", help="list a vessel's dry-docking events")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=h.cmd_drydock_list)


def _register_safety(sub, h) -> None:
    p = sub.add_parser("safety", help="QHSE — near-miss/incident/audit/inspection reporting")
    safety_sub = p.add_subparsers(dest="safety_command", required=True)
    p_report = safety_sub.add_parser(
        "report",
        help="report a near-miss, incident, audit, or inspection (no role restriction — anyone can report)",
    )
    p_report.add_argument("vessel")
    p_report.add_argument("incident_type", choices=["near_miss", "incident", "audit", "inspection"])
    p_report.add_argument("description")
    p_report.add_argument("--severity", default=None, choices=["low", "medium", "high", "critical"])
    p_report.add_argument(
        "--find-similar",
        action="store_true",
        help="after reporting, retrieve similar past incidents from the ingested corpus",
    )
    _add_user_flag(p_report)
    p_report.set_defaults(func=h.cmd_safety_report)
    p_list = safety_sub.add_parser("list", help="list a vessel's safety reports, newest first")
    p_list.add_argument("vessel")
    p_list.add_argument("--status", default=None, choices=["open", "closed"])
    p_list.set_defaults(func=h.cmd_safety_list)
    p_close = safety_sub.add_parser("close", help="close a safety report with a corrective action")
    p_close.add_argument("incident_id", type=int)
    p_close.add_argument("--corrective-action", default=None)
    _add_user_flag(p_close)
    p_close.set_defaults(func=h.cmd_safety_close)
    p_reportable = safety_sub.add_parser(
        "reportable",
        help="list open critical incidents that trigger SOLAS I/21's flag-State casualty report",
    )
    p_reportable.set_defaults(func=h.cmd_safety_reportable)


def _register_fleet(sub, h) -> None:
    p = sub.add_parser(
        "fleet", help="read-only cross-vessel rollup — open incidents, cert expiries, drydocks"
    )
    fleet_sub = p.add_subparsers(dest="fleet_command", required=True)
    p_status = fleet_sub.add_parser("status", help="fleet-wide safety/compliance/drydock snapshot")
    p_status.add_argument(
        "--cert-days", type=int, default=30, help="STCW cert look-ahead window in days"
    )
    p_status.add_argument(
        "--drydock-days", type=int, default=90, help="drydock look-ahead window in days"
    )
    p_status.set_defaults(func=h.cmd_fleet_status)


def register_all(sub, handlers) -> None:
    """Adds every operations subcommand to `sub`; `handlers` supplies the cmd_* functions."""
    _register_user(sub, handlers)
    _register_vessel(sub, handlers)
    _register_crew(sub, handlers)
    _register_log(sub, handlers)
    _register_equipment(sub, handlers)
    _register_parts(sub, handlers)
    _register_maintenance(sub, handlers)
    _register_fuel(sub, handlers)
    _register_procurement(sub, handlers)
    _register_drydock(sub, handlers)
    _register_safety(sub, handlers)
    _register_fleet(sub, handlers)
