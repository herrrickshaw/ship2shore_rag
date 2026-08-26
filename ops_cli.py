"""CLI subcommands for the operations module (vessels, crew, logbooks,
EPC/maintenance, fuel). Kept separate from cli.py because there are a lot of
these — see README "Operations module" for the entity list and IAM model.
"""

from ops import store
from ops.auth import AuthError, current_user_name, require_role


def _actor(args):
    """Resolves --user/SHIP2SHORE_USER to a users row, or None if unset."""
    name = current_user_name(getattr(args, "user", None))
    return store.get_user_by_name(name) if name else None


def _authorize(args, action: str) -> None:
    try:
        require_role(_actor(args), action)
    except AuthError as e:
        raise SystemExit(f"permission denied: {e}")


def _resolve_vessel(name_or_imo: str) -> dict:
    vessel = store.get_vessel(name_or_imo)
    if vessel is None:
        raise SystemExit(
            f"no vessel matching {name_or_imo!r} — add it first with `cli.py vessel add`"
        )
    return vessel


# ---- users ------------------------------------------------------------------


def cmd_user_add(args):
    uid = store.add_user(args.name, args.role, email=args.email)
    print(f"added user #{uid}: {args.name} ({args.role})")


def cmd_user_list(_args):
    for u in store.list_users():
        print(f"#{u['id']}  {u['name']:<20} {u['role']:<15} {u.get('email') or ''}")


# ---- vessels ------------------------------------------------------------------


def cmd_vessel_add(args):
    _authorize(args, "vessel:add")
    fields = {
        k: v
        for k, v in {
            "flag": args.flag,
            "vessel_type": args.type,
            "gross_tonnage": args.gt,
            "deadweight": args.dwt,
            "build_year": args.build_year,
            "classification_society": args.class_society,
            "main_engine": args.main_engine,
        }.items()
        if v is not None
    }
    vid = store.add_vessel(args.name, imo_number=args.imo, **fields)
    print(f"added vessel #{vid}: {args.name}")


def cmd_vessel_list(_args):
    for v in store.list_vessels():
        print(
            f"#{v['id']}  {v['name']:<25} IMO {v.get('imo_number') or '-':<10} {v.get('vessel_type') or ''}"
        )


# ---- crew (seafarer onboarding) -----------------------------------------------


def cmd_crew_add(args):
    _authorize(args, "crew:signon")
    vessel = _resolve_vessel(args.vessel)
    fields = {
        k: v
        for k, v in {
            "nationality": args.nationality,
            "stcw_cert_number": args.stcw_number,
            "stcw_cert_expiry": args.stcw_expiry,
            "sign_on_date": args.sign_on,
        }.items()
        if v is not None
    }
    cid = store.add_crew(args.name, args.rank, vessel_id=vessel["id"], **fields)
    print(f"added crew #{cid}: {args.name} ({args.rank}) on {vessel['name']}")


def cmd_crew_list(args):
    vessel_id = _resolve_vessel(args.vessel)["id"] if args.vessel else None
    for c in store.list_crew(vessel_id=vessel_id):
        status = f"signed off {c['sign_off_date']}" if c.get("sign_off_date") else "aboard"
        print(f"#{c['id']}  {c['name']:<20} {c['rank']:<20} {status}")


def cmd_crew_signoff(args):
    _authorize(args, "crew:signoff")
    store.crew_signoff(args.crew_id, args.date)
    print(f"crew #{args.crew_id} signed off {args.date}")


def cmd_crew_expiring_certs(args):
    certs = store.list_expiring_certs(days_ahead=args.days)
    if not certs:
        print(f"no STCW certificates expiring within {args.days} days")
        return
    for c in certs:
        print(
            f"#{c['id']}  {c['name']:<20} {c['rank']:<20} {c['vessel_name']:<20} expires {c['stcw_cert_expiry']}"
        )


# ---- log_entries (master/captain/deck/engine log) -------------------------


def cmd_log_add(args):
    _authorize(args, f"log:{args.log_type}")
    vessel = _resolve_vessel(args.vessel)
    actor = _actor(args)
    fields = {
        k: v for k, v in {"latitude": args.lat, "longitude": args.lon}.items() if v is not None
    }
    lid = store.add_log_entry(
        vessel["id"], args.log_type, args.text, logged_by=actor["id"] if actor else None, **fields
    )
    print(f"added {args.log_type} log entry #{lid} on {vessel['name']}")


def cmd_log_list(args):
    vessel = _resolve_vessel(args.vessel)
    for entry in store.list_log_entries(vessel["id"], log_type=args.type):
        print(
            f"#{entry['id']}  {entry['entry_time']}  [{entry['log_type']}]  {entry['entry_text']}"
        )


# ---- equipment / EPC (spare parts) / maintenance ---------------------------


def cmd_equipment_add(args):
    _authorize(args, "equipment:add")
    vessel = _resolve_vessel(args.vessel)
    fields = {
        k: v
        for k, v in {
            "equipment_type": args.type,
            "manufacturer": args.manufacturer,
            "model": args.model,
            "serial_number": args.serial,
        }.items()
        if v is not None
    }
    eid = store.add_equipment(vessel["id"], args.name, **fields)
    print(f"added equipment #{eid}: {args.name} on {vessel['name']}")


def cmd_equipment_list(args):
    vessel = _resolve_vessel(args.vessel)
    for e in store.list_equipment(vessel["id"]):
        print(f"#{e['id']}  {e['name']:<25} {e.get('manufacturer') or ''} {e.get('model') or ''}")


def cmd_parts_add(args):
    _authorize(args, "parts:add")
    fields = {
        k: v
        for k, v in {"manufacturer": args.manufacturer, "stock_quantity": args.qty}.items()
        if v is not None
    }
    pid = store.add_part(args.equipment_id, args.part_number, args.part_name, **fields)
    print(f"added part #{pid}: {args.part_number} — {args.part_name}")


def cmd_parts_list(args):
    for p in store.list_parts(args.equipment_id):
        print(f"#{p['id']}  {p['part_number']:<15} {p['part_name']:<25} qty {p['stock_quantity']}")


def cmd_maintenance_add(args):
    _authorize(args, "maintenance:add")
    actor = _actor(args)
    fields = {
        k: v
        for k, v in {"running_hours": args.hours, "parts_used": args.parts_used}.items()
        if v is not None
    }
    mid = store.add_maintenance(
        args.equipment_id,
        args.job_type,
        args.description,
        performed_by=actor["id"] if actor else None,
        **fields,
    )
    print(f"added maintenance job #{mid}: {args.job_type} — {args.description}")


def cmd_maintenance_list(args):
    for m in store.list_maintenance(args.equipment_id):
        print(f"#{m['id']}  {m['job_date']}  [{m['job_type']}]  {m['description']}")


# ---- fuel_log ---------------------------------------------------------------


def cmd_fuel_add(args):
    _authorize(args, "fuel:add")
    vessel = _resolve_vessel(args.vessel)
    fields = {
        k: v
        for k, v in {"rob_after_mt": args.rob, "location": args.location}.items()
        if v is not None
    }
    fid = store.add_fuel_entry(
        vessel["id"], args.fuel_type, args.event_type, args.quantity_mt, **fields
    )
    print(f"added fuel log #{fid}: {args.event_type} {args.quantity_mt}mt {args.fuel_type}")


def cmd_fuel_list(args):
    vessel = _resolve_vessel(args.vessel)
    for f in store.list_fuel_log(vessel["id"]):
        print(
            f"#{f['id']}  {f['log_date']}  [{f['event_type']}]  {f['quantity_mt']}mt {f['fuel_type']}  ROB {f.get('rob_after_mt') or '-'}"
        )


# ---- procurement (purchase-to-pay) -----------------------------------------


def cmd_procurement_add(args):
    _authorize(args, "procurement:add")
    vessel = _resolve_vessel(args.vessel)
    actor = _actor(args)
    fields = {
        k: v
        for k, v in {
            "equipment_id": args.equipment_id,
            "supplier": args.supplier,
            "total_cost": args.cost,
            "currency": args.currency,
            "expected_delivery": args.expected_delivery,
        }.items()
        if v is not None
    }
    pid = store.add_purchase_order(
        vessel["id"], args.items, requested_by=actor["id"] if actor else None, **fields
    )
    print(f"added purchase order #{pid} for {vessel['name']}: {args.items} (status: requested)")


def cmd_procurement_list(args):
    vessel = _resolve_vessel(args.vessel)
    for po in store.list_purchase_orders(vessel["id"], status=args.status):
        print(
            f"#{po['id']}  [{po['status']}]  {po['items']}  supplier={po.get('supplier') or '-'}  cost={po.get('total_cost') or '-'}"
        )


def cmd_procurement_approve(args):
    _authorize(args, "procurement:approve")
    actor = _actor(args)
    store.approve_purchase_order(args.po_id, actor["id"] if actor else None)
    print(f"purchase order #{args.po_id} approved")


def cmd_procurement_status(args):
    _authorize(args, "procurement:approve")
    store.update_purchase_order_status(args.po_id, args.status)
    print(f"purchase order #{args.po_id} status set to {args.status}")


# ---- drydock_events -----------------------------------------------------------


def cmd_drydock_add(args):
    _authorize(args, "drydock:add")
    vessel = _resolve_vessel(args.vessel)
    actor = _actor(args)
    fields = {
        k: v
        for k, v in {
            "yard": args.yard,
            "location": args.location,
            "planned_start": args.start,
            "planned_end": args.end,
            "scope_description": args.scope,
            "total_cost": args.cost,
            "currency": args.currency,
        }.items()
        if v is not None
    }
    did = store.add_drydock_event(
        vessel["id"], coordinated_by=actor["id"] if actor else None, **fields
    )
    print(f"added drydock event #{did} for {vessel['name']}")


def cmd_drydock_list(args):
    vessel = _resolve_vessel(args.vessel)
    for d in store.list_drydock_events(vessel["id"]):
        print(
            f"#{d['id']}  [{d['status']}]  {d.get('yard') or '-'}  {d.get('planned_start') or '-'} to {d.get('planned_end') or '-'}"
        )


# ---- safety_incidents (QHSE) ------------------------------------------------


def cmd_safety_report(args):
    # Deliberately unrestricted — see ops/auth.py's comment on "safety:report".
    vessel = _resolve_vessel(args.vessel)
    actor = _actor(args)
    fields = {k: v for k, v in {"severity": args.severity}.items() if v is not None}
    sid = store.add_safety_incident(
        vessel["id"],
        args.incident_type,
        args.description,
        reported_by=actor["id"] if actor else None,
        **fields,
    )
    print(f"reported {args.incident_type} #{sid} on {vessel['name']} (status: open)")


def cmd_safety_list(args):
    vessel = _resolve_vessel(args.vessel)
    for s in store.list_safety_incidents(vessel["id"], status=args.status):
        print(
            f"#{s['id']}  {s['incident_date']}  [{s['incident_type']}/{s['status']}]  {s['description']}"
        )


def cmd_safety_reportable(_args):
    incidents = store.list_reportable_incidents()
    if not incidents:
        print("no open critical incidents requiring a flag-State casualty report")
        return
    for s in incidents:
        print(
            f"#{s['id']}  {s['incident_date']}  {s['vessel_name']:<20} [{s['incident_type']}]  {s['description']}"
        )


def cmd_safety_close(args):
    _authorize(args, "safety:close")
    actor = _actor(args)
    store.close_safety_incident(
        args.incident_id, actor["id"] if actor else None, corrective_action=args.corrective_action
    )
    print(f"safety incident #{args.incident_id} closed")


def _add_user_flag(parser):
    parser.add_argument("--user", default=None, help="acting user's name (or set SHIP2SHORE_USER)")


def register(sub) -> None:
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
    p_add.set_defaults(func=cmd_user_add)
    user_sub.add_parser("list", help="list registered users").set_defaults(func=cmd_user_list)

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
    p_add.set_defaults(func=cmd_vessel_add)
    vessel_sub.add_parser("list", help="list registered vessels").set_defaults(func=cmd_vessel_list)

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
    p_add.set_defaults(func=cmd_crew_add)
    p_list = crew_sub.add_parser("list", help="list crew, optionally filtered to one vessel")
    p_list.add_argument("--vessel", default=None)
    p_list.set_defaults(func=cmd_crew_list)
    p_signoff = crew_sub.add_parser("signoff", help="sign a crew member off")
    p_signoff.add_argument("crew_id", type=int)
    p_signoff.add_argument("--date", required=True, help="sign-off date (YYYY-MM-DD)")
    _add_user_flag(p_signoff)
    p_signoff.set_defaults(func=cmd_crew_signoff)
    p_expiring = crew_sub.add_parser(
        "expiring-certs",
        help="list currently-aboard crew whose STCW certificate has expired or is expiring soon",
    )
    p_expiring.add_argument(
        "--days", type=int, default=30, help="look-ahead window in days (default: 30)"
    )
    p_expiring.set_defaults(func=cmd_crew_expiring_certs)

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
    p_add.set_defaults(func=cmd_log_add)
    p_list = log_sub.add_parser("list", help="list a vessel's log entries, newest first")
    p_list.add_argument("vessel")
    p_list.add_argument("--type", default=None, choices=["deck", "engine", "captain"])
    p_list.set_defaults(func=cmd_log_list)

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
    p_add.set_defaults(func=cmd_equipment_add)
    p_list = eq_sub.add_parser("list", help="list a vessel's equipment")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=cmd_equipment_list)

    p = sub.add_parser("parts", help="EPC — electronic parts catalog")
    parts_sub = p.add_subparsers(dest="parts_command", required=True)
    p_add = parts_sub.add_parser("add", help="add a spare part to an equipment's catalog entry")
    p_add.add_argument("equipment_id", type=int)
    p_add.add_argument("part_number")
    p_add.add_argument("part_name")
    p_add.add_argument("--manufacturer", default=None)
    p_add.add_argument("--qty", type=int, default=None, help="stock quantity")
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_parts_add)
    p_list = parts_sub.add_parser("list", help="list an equipment's spare parts")
    p_list.add_argument("equipment_id", type=int)
    p_list.set_defaults(func=cmd_parts_list)

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
    p_add.set_defaults(func=cmd_maintenance_add)
    p_list = maint_sub.add_parser(
        "list", help="list an equipment's maintenance history, newest first"
    )
    p_list.add_argument("equipment_id", type=int)
    p_list.set_defaults(func=cmd_maintenance_list)

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
    p_add.set_defaults(func=cmd_fuel_add)
    p_list = fuel_sub.add_parser("list", help="list a vessel's fuel log, newest first")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=cmd_fuel_list)

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
    p_add.set_defaults(func=cmd_procurement_add)
    p_list = proc_sub.add_parser("list", help="list a vessel's purchase orders")
    p_list.add_argument("vessel")
    p_list.add_argument(
        "--status",
        default=None,
        choices=["requested", "approved", "ordered", "received", "cancelled"],
    )
    p_list.set_defaults(func=cmd_procurement_list)
    p_approve = proc_sub.add_parser("approve", help="approve a requested purchase order")
    p_approve.add_argument("po_id", type=int)
    _add_user_flag(p_approve)
    p_approve.set_defaults(func=cmd_procurement_approve)
    p_status = proc_sub.add_parser(
        "status", help="update a purchase order's status (e.g. ordered, received)"
    )
    p_status.add_argument("po_id", type=int)
    p_status.add_argument(
        "status", choices=["requested", "approved", "ordered", "received", "cancelled"]
    )
    _add_user_flag(p_status)
    p_status.set_defaults(func=cmd_procurement_status)

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
    p_add.set_defaults(func=cmd_drydock_add)
    p_list = dd_sub.add_parser("list", help="list a vessel's dry-docking events")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=cmd_drydock_list)

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
    _add_user_flag(p_report)
    p_report.set_defaults(func=cmd_safety_report)
    p_list = safety_sub.add_parser("list", help="list a vessel's safety reports, newest first")
    p_list.add_argument("vessel")
    p_list.add_argument("--status", default=None, choices=["open", "closed"])
    p_list.set_defaults(func=cmd_safety_list)
    p_close = safety_sub.add_parser("close", help="close a safety report with a corrective action")
    p_close.add_argument("incident_id", type=int)
    p_close.add_argument("--corrective-action", default=None)
    _add_user_flag(p_close)
    p_close.set_defaults(func=cmd_safety_close)
    p_reportable = safety_sub.add_parser(
        "reportable",
        help="list open critical incidents that trigger SOLAS I/21's flag-State casualty report",
    )
    p_reportable.set_defaults(func=cmd_safety_reportable)
