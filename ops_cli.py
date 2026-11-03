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

    if args.find_similar:
        from rag.similar_incidents import find_similar_incidents

        similar = find_similar_incidents(args.description)
        if similar:
            print("\nSimilar past incidents in the ingested corpus:")
            for i, p in enumerate(similar, 1):
                print(f"[{i}] {p['title']} ({p['url']}) — score {p['score']:.4f}")


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


# ---- fleet (cross-vessel, read-only rollup) --------------------------------


def cmd_fleet_status(args):
    status = store.fleet_status(
        cert_days_ahead=args.cert_days, drydock_days_ahead=args.drydock_days
    )
    print(f"Fleet: {status['vessel_count']} vessel(s)")
    print(f"Open safety incidents: {len(status['open_incidents'])}")
    for sev, n in sorted(status["open_incidents_by_severity"].items()):
        print(f"  {sev}: {n}")
    print(f"STCW certs expiring within {args.cert_days}d: {len(status['certs_expiring'])}")
    for c in status["certs_expiring"]:
        print(
            f"  {c['name']} ({c['rank']}) on {c['vessel_name']} — expires {c['stcw_cert_expiry']}"
        )
    print(f"Drydocks starting within {args.drydock_days}d: {len(status['drydocks_upcoming'])}")
    for d in status["drydocks_upcoming"]:
        print(f"  {d['vessel_name']} — {d.get('yard') or '-'} starting {d['planned_start']}")


def register(sub) -> None:
    """Adds the operations subcommands (user, vessel, crew, ...) to cli.py's subparsers."""
    import sys

    from ops_cli_parsers import register_all

    register_all(sub, sys.modules[__name__])
