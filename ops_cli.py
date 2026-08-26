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
        raise SystemExit(f"no vessel matching {name_or_imo!r} — add it first with `cli.py vessel add`")
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
        print(f"#{v['id']}  {v['name']:<25} IMO {v.get('imo_number') or '-':<10} {v.get('vessel_type') or ''}")


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


# ---- log_entries (master/captain/deck/engine log) -------------------------

def cmd_log_add(args):
    _authorize(args, f"log:{args.log_type}")
    vessel = _resolve_vessel(args.vessel)
    actor = _actor(args)
    fields = {k: v for k, v in {"latitude": args.lat, "longitude": args.lon}.items() if v is not None}
    lid = store.add_log_entry(
        vessel["id"], args.log_type, args.text, logged_by=actor["id"] if actor else None, **fields
    )
    print(f"added {args.log_type} log entry #{lid} on {vessel['name']}")


def cmd_log_list(args):
    vessel = _resolve_vessel(args.vessel)
    for entry in store.list_log_entries(vessel["id"], log_type=args.type):
        print(f"#{entry['id']}  {entry['entry_time']}  [{entry['log_type']}]  {entry['entry_text']}")


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
        k: v for k, v in {"manufacturer": args.manufacturer, "stock_quantity": args.qty}.items() if v is not None
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
        args.equipment_id, args.job_type, args.description, performed_by=actor["id"] if actor else None, **fields
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
        k: v for k, v in {"rob_after_mt": args.rob, "location": args.location}.items() if v is not None
    }
    fid = store.add_fuel_entry(vessel["id"], args.fuel_type, args.event_type, args.quantity_mt, **fields)
    print(f"added fuel log #{fid}: {args.event_type} {args.quantity_mt}mt {args.fuel_type}")


def cmd_fuel_list(args):
    vessel = _resolve_vessel(args.vessel)
    for f in store.list_fuel_log(vessel["id"]):
        print(f"#{f['id']}  {f['log_date']}  [{f['event_type']}]  {f['quantity_mt']}mt {f['fuel_type']}  ROB {f.get('rob_after_mt') or '-'}")


def _add_user_flag(parser):
    parser.add_argument("--user", default=None, help="acting user's name (or set SHIP2SHORE_USER)")


def register(sub) -> None:
    p = sub.add_parser("user")
    user_sub = p.add_subparsers(dest="user_command", required=True)
    p_add = user_sub.add_parser("add")
    p_add.add_argument("name")
    p_add.add_argument("--role", required=True, choices=["master", "chief_engineer", "officer", "deck_crew", "engine_crew", "shore_staff"])
    p_add.add_argument("--email", default=None)
    p_add.set_defaults(func=cmd_user_add)
    user_sub.add_parser("list").set_defaults(func=cmd_user_list)

    p = sub.add_parser("vessel")
    vessel_sub = p.add_subparsers(dest="vessel_command", required=True)
    p_add = vessel_sub.add_parser("add")
    p_add.add_argument("name")
    p_add.add_argument("--imo", default=None)
    p_add.add_argument("--flag", default=None)
    p_add.add_argument("--type", default=None)
    p_add.add_argument("--gt", type=float, default=None)
    p_add.add_argument("--dwt", type=float, default=None)
    p_add.add_argument("--build-year", type=int, default=None)
    p_add.add_argument("--class-society", default=None)
    p_add.add_argument("--main-engine", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_vessel_add)
    vessel_sub.add_parser("list").set_defaults(func=cmd_vessel_list)

    p = sub.add_parser("crew")
    crew_sub = p.add_subparsers(dest="crew_command", required=True)
    p_add = crew_sub.add_parser("add")
    p_add.add_argument("name")
    p_add.add_argument("rank")
    p_add.add_argument("--vessel", required=True, help="vessel name or IMO number")
    p_add.add_argument("--nationality", default=None)
    p_add.add_argument("--stcw-number", default=None)
    p_add.add_argument("--stcw-expiry", default=None)
    p_add.add_argument("--sign-on", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_crew_add)
    p_list = crew_sub.add_parser("list")
    p_list.add_argument("--vessel", default=None)
    p_list.set_defaults(func=cmd_crew_list)
    p_signoff = crew_sub.add_parser("signoff")
    p_signoff.add_argument("crew_id", type=int)
    p_signoff.add_argument("--date", required=True)
    _add_user_flag(p_signoff)
    p_signoff.set_defaults(func=cmd_crew_signoff)

    p = sub.add_parser("log")
    log_sub = p.add_subparsers(dest="log_command", required=True)
    p_add = log_sub.add_parser("add")
    p_add.add_argument("vessel", help="vessel name or IMO number")
    p_add.add_argument("log_type", choices=["deck", "engine", "captain"])
    p_add.add_argument("text")
    p_add.add_argument("--lat", type=float, default=None)
    p_add.add_argument("--lon", type=float, default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_log_add)
    p_list = log_sub.add_parser("list")
    p_list.add_argument("vessel")
    p_list.add_argument("--type", default=None, choices=["deck", "engine", "captain"])
    p_list.set_defaults(func=cmd_log_list)

    p = sub.add_parser("equipment")
    eq_sub = p.add_subparsers(dest="equipment_command", required=True)
    p_add = eq_sub.add_parser("add")
    p_add.add_argument("vessel")
    p_add.add_argument("name")
    p_add.add_argument("--type", default=None)
    p_add.add_argument("--manufacturer", default=None)
    p_add.add_argument("--model", default=None)
    p_add.add_argument("--serial", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_equipment_add)
    p_list = eq_sub.add_parser("list")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=cmd_equipment_list)

    p = sub.add_parser("parts", help="EPC — electronic parts catalog")
    parts_sub = p.add_subparsers(dest="parts_command", required=True)
    p_add = parts_sub.add_parser("add")
    p_add.add_argument("equipment_id", type=int)
    p_add.add_argument("part_number")
    p_add.add_argument("part_name")
    p_add.add_argument("--manufacturer", default=None)
    p_add.add_argument("--qty", type=int, default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_parts_add)
    p_list = parts_sub.add_parser("list")
    p_list.add_argument("equipment_id", type=int)
    p_list.set_defaults(func=cmd_parts_list)

    p = sub.add_parser("maintenance")
    maint_sub = p.add_subparsers(dest="maintenance_command", required=True)
    p_add = maint_sub.add_parser("add")
    p_add.add_argument("equipment_id", type=int)
    p_add.add_argument("job_type", choices=["scheduled", "breakdown", "repair", "inspection"])
    p_add.add_argument("description")
    p_add.add_argument("--hours", type=float, default=None, help="running hours at time of job")
    p_add.add_argument("--parts-used", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_maintenance_add)
    p_list = maint_sub.add_parser("list")
    p_list.add_argument("equipment_id", type=int)
    p_list.set_defaults(func=cmd_maintenance_list)

    p = sub.add_parser("fuel")
    fuel_sub = p.add_subparsers(dest="fuel_command", required=True)
    p_add = fuel_sub.add_parser("add")
    p_add.add_argument("vessel")
    p_add.add_argument("fuel_type", help="e.g. VLSFO, MGO, LSMGO")
    p_add.add_argument("event_type", choices=["bunkering", "consumption", "ROB"])
    p_add.add_argument("quantity_mt", type=float)
    p_add.add_argument("--rob", type=float, default=None, help="remaining on board after this event, in mt")
    p_add.add_argument("--location", default=None)
    _add_user_flag(p_add)
    p_add.set_defaults(func=cmd_fuel_add)
    p_list = fuel_sub.add_parser("list")
    p_list.add_argument("vessel")
    p_list.set_defaults(func=cmd_fuel_list)
