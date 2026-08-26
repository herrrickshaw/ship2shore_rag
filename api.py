"""FastAPI wrapper around ops/store.py — the operations module (vessels, crew,
logbooks, EPC/maintenance, fuel, procurement, dry-docking, QHSE) as a REST
API, for a frontend (e.g. built on Lovable) to consume. Uses the exact same
IAM as the CLI (ops/auth.py) — the acting user is passed as `X-User` header,
looked up in the `users` table, and role-checked before restricted actions.

`X-User` is attribution, not authentication — it's a self-reported name with
no secret behind it, exactly like `--user` on the CLI. That's fine for a
trusted local CLI; it is NOT fine for an API reachable from the public
internet, where anyone could claim to be "Captain Ahab". API_KEY (below) is
the actual access gate for deployment — see README "Operations module API".

Deliberately does NOT wrap rag/pipeline.py (`ask`) — this is the ops-data
surface only, matching what was asked for.

Every endpoint is plain `def`, not `async def` — deliberately. ops/store.py
is entirely sync (psycopg/sqlite3, no awaitable calls), and a plain `def`
endpoint runs in Starlette's worker thread pool automatically, so that
blocking I/O never freezes the event loop. Making an endpoint `async def`
without also awaiting every blocking call inside it is the classic FastAPI
mistake where one slow request stalls every other concurrent request on
the same process — don't "modernize" this to async without threading
async I/O all the way through ops/store.py first (psycopg has an async
API; sqlite3 doesn't have an official one).
"""

import os
import secrets
import sqlite3
from datetime import date
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ops import store
from ops.auth import AuthError, require_role

# Shared-secret gate for the whole API. If API_KEY isn't set, one is generated
# at startup and printed once — the API is never silently open. Set your own
# API_KEY before deploying anywhere reachable from the internet, and share it
# only with whoever should be able to use the app.
API_KEY = os.environ.get("API_KEY") or secrets.token_urlsafe(24)
if not os.environ.get("API_KEY"):
    print(f"API_KEY not set — generated one for this run: {API_KEY}")
    print("Set API_KEY in your environment to persist it across restarts.")


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not secrets.compare_digest(x_api_key or "", API_KEY):
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


app = FastAPI(
    title="ship2shore_rag operations API", version="0.1.0", dependencies=[Depends(verify_api_key)]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your frontend's origin before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(psycopg.errors.UniqueViolation)
@app.exception_handler(sqlite3.IntegrityError)
def handle_unique_violation(_request: Request, _exc: Exception) -> JSONResponse:
    # Without this, a duplicate (e.g. an IMO number or a part number already
    # registered) surfaces as a raw, unhandled 500 with an empty body — bad
    # for any client, and confusing to debug. A clean 409 with a real message
    # is what a duplicate-key conflict actually is.
    return JSONResponse(
        status_code=409, content={"detail": "a record with this unique value already exists"}
    )


Role = Literal["master", "chief_engineer", "officer", "deck_crew", "engine_crew", "shore_staff"]


def current_user(x_user: str | None = Header(default=None)) -> dict | None:
    return store.get_user_by_name(x_user) if x_user else None


def authorize(user: dict | None, action: str) -> None:
    try:
        require_role(user, action)
    except AuthError as e:
        raise HTTPException(status_code=403, detail=str(e))


def _actor_id(user: dict | None) -> int | None:
    return user["id"] if user else None


def resolve_vessel(name_or_imo: str) -> dict:
    vessel = store.get_vessel(name_or_imo)
    if vessel is None:
        raise HTTPException(status_code=404, detail=f"no vessel matching {name_or_imo!r}")
    return vessel


# ---- users ------------------------------------------------------------------


class UserIn(BaseModel):
    name: str
    role: Role
    email: str | None = None


@app.post("/users")
def create_user(body: UserIn):
    uid = store.add_user(body.name, body.role, email=body.email)
    return {"id": uid}


@app.get("/users")
def list_users():
    return store.list_users()


# ---- vessels ------------------------------------------------------------------


class VesselIn(BaseModel):
    name: str
    imo_number: str | None = None
    flag: str | None = None
    vessel_type: str | None = None
    gross_tonnage: float | None = None
    deadweight: float | None = None
    build_year: int | None = None
    classification_society: str | None = None
    main_engine: str | None = None


@app.post("/vessels")
def create_vessel(body: VesselIn, user: dict | None = Depends(current_user)):
    authorize(user, "vessel:add")
    fields = body.model_dump(exclude={"name", "imo_number"}, exclude_none=True)
    vid = store.add_vessel(body.name, imo_number=body.imo_number, **fields)
    return {"id": vid}


@app.get("/vessels")
def list_vessels():
    return store.list_vessels()


@app.get("/vessels/{name_or_imo}")
def get_vessel(name_or_imo: str):
    return resolve_vessel(name_or_imo)


# ---- crew (seafarer onboarding) -----------------------------------------------


class CrewIn(BaseModel):
    name: str
    rank: str
    vessel: str  # name or IMO
    nationality: str | None = None
    stcw_cert_number: str | None = None
    stcw_cert_expiry: date | None = None
    sign_on_date: date | None = None


@app.post("/crew")
def create_crew(body: CrewIn, user: dict | None = Depends(current_user)):
    authorize(user, "crew:signon")
    vessel = resolve_vessel(body.vessel)
    fields = body.model_dump(exclude={"name", "rank", "vessel"}, exclude_none=True)
    cid = store.add_crew(body.name, body.rank, vessel_id=vessel["id"], **fields)
    return {"id": cid}


@app.get("/crew")
def list_crew(vessel: str | None = None):
    vessel_id = resolve_vessel(vessel)["id"] if vessel else None
    return store.list_crew(vessel_id=vessel_id)


class SignoffIn(BaseModel):
    sign_off_date: date


@app.post("/crew/{crew_id}/signoff")
def signoff_crew(crew_id: int, body: SignoffIn, user: dict | None = Depends(current_user)):
    authorize(user, "crew:signoff")
    store.crew_signoff(crew_id, str(body.sign_off_date))
    return {"ok": True}


# ---- log_entries -------------------------------------------------------------


class LogEntryIn(BaseModel):
    log_type: Literal["deck", "engine", "captain"]
    entry_text: str
    latitude: float | None = None
    longitude: float | None = None


@app.post("/vessels/{name_or_imo}/log")
def create_log_entry(name_or_imo: str, body: LogEntryIn, user: dict | None = Depends(current_user)):
    authorize(user, f"log:{body.log_type}")
    vessel = resolve_vessel(name_or_imo)
    fields = body.model_dump(exclude={"log_type", "entry_text"}, exclude_none=True)
    lid = store.add_log_entry(
        vessel["id"], body.log_type, body.entry_text, logged_by=_actor_id(user), **fields
    )
    return {"id": lid}


@app.get("/vessels/{name_or_imo}/log")
def list_log_entries(
    name_or_imo: str, log_type: Literal["deck", "engine", "captain"] | None = None
):
    vessel = resolve_vessel(name_or_imo)
    return store.list_log_entries(vessel["id"], log_type=log_type)


# ---- equipment / EPC (spare parts) / maintenance ---------------------------


class EquipmentIn(BaseModel):
    name: str
    equipment_type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None


@app.post("/vessels/{name_or_imo}/equipment")
def create_equipment(
    name_or_imo: str, body: EquipmentIn, user: dict | None = Depends(current_user)
):
    authorize(user, "equipment:add")
    vessel = resolve_vessel(name_or_imo)
    fields = body.model_dump(exclude={"name"}, exclude_none=True)
    eid = store.add_equipment(vessel["id"], body.name, **fields)
    return {"id": eid}


@app.get("/vessels/{name_or_imo}/equipment")
def list_equipment(name_or_imo: str):
    vessel = resolve_vessel(name_or_imo)
    return store.list_equipment(vessel["id"])


class PartIn(BaseModel):
    part_number: str
    part_name: str
    manufacturer: str | None = None
    stock_quantity: int | None = None


@app.post("/equipment/{equipment_id}/parts")
def create_part(equipment_id: int, body: PartIn, user: dict | None = Depends(current_user)):
    authorize(user, "parts:add")
    fields = body.model_dump(exclude={"part_number", "part_name"}, exclude_none=True)
    pid = store.add_part(equipment_id, body.part_number, body.part_name, **fields)
    return {"id": pid}


@app.get("/equipment/{equipment_id}/parts")
def list_parts(equipment_id: int):
    return store.list_parts(equipment_id)


class MaintenanceIn(BaseModel):
    job_type: Literal["scheduled", "breakdown", "repair", "inspection"]
    description: str
    running_hours: float | None = None
    parts_used: str | None = None


@app.post("/equipment/{equipment_id}/maintenance")
def create_maintenance(
    equipment_id: int, body: MaintenanceIn, user: dict | None = Depends(current_user)
):
    authorize(user, "maintenance:add")
    fields = body.model_dump(exclude={"job_type", "description"}, exclude_none=True)
    mid = store.add_maintenance(
        equipment_id, body.job_type, body.description, performed_by=_actor_id(user), **fields
    )
    return {"id": mid}


@app.get("/equipment/{equipment_id}/maintenance")
def list_maintenance(equipment_id: int):
    return store.list_maintenance(equipment_id)


# ---- fuel_log -----------------------------------------------------------------


class FuelIn(BaseModel):
    fuel_type: str
    event_type: Literal["bunkering", "consumption", "ROB"]
    quantity_mt: float
    rob_after_mt: float | None = None
    location: str | None = None


@app.post("/vessels/{name_or_imo}/fuel")
def create_fuel_entry(name_or_imo: str, body: FuelIn, user: dict | None = Depends(current_user)):
    authorize(user, "fuel:add")
    vessel = resolve_vessel(name_or_imo)
    fields = body.model_dump(exclude={"fuel_type", "event_type", "quantity_mt"}, exclude_none=True)
    fid = store.add_fuel_entry(
        vessel["id"], body.fuel_type, body.event_type, body.quantity_mt, **fields
    )
    return {"id": fid}


@app.get("/vessels/{name_or_imo}/fuel")
def list_fuel(name_or_imo: str):
    vessel = resolve_vessel(name_or_imo)
    return store.list_fuel_log(vessel["id"])


# ---- procurement --------------------------------------------------------------


class PurchaseOrderIn(BaseModel):
    items: str
    equipment_id: int | None = None
    supplier: str | None = None
    total_cost: float | None = None
    currency: str | None = None
    expected_delivery: date | None = None


@app.post("/vessels/{name_or_imo}/procurement")
def create_purchase_order(
    name_or_imo: str, body: PurchaseOrderIn, user: dict | None = Depends(current_user)
):
    authorize(user, "procurement:add")
    vessel = resolve_vessel(name_or_imo)
    fields = body.model_dump(exclude={"items"}, exclude_none=True)
    pid = store.add_purchase_order(vessel["id"], body.items, requested_by=_actor_id(user), **fields)
    return {"id": pid}


@app.get("/vessels/{name_or_imo}/procurement")
def list_purchase_orders(name_or_imo: str, status: str | None = None):
    vessel = resolve_vessel(name_or_imo)
    return store.list_purchase_orders(vessel["id"], status=status)


@app.post("/procurement/{po_id}/approve")
def approve_purchase_order(po_id: int, user: dict | None = Depends(current_user)):
    authorize(user, "procurement:approve")
    store.approve_purchase_order(po_id, _actor_id(user))
    return {"ok": True}


class StatusIn(BaseModel):
    status: Literal["requested", "approved", "ordered", "received", "cancelled"]


@app.patch("/procurement/{po_id}/status")
def update_purchase_order_status(
    po_id: int, body: StatusIn, user: dict | None = Depends(current_user)
):
    authorize(user, "procurement:approve")
    store.update_purchase_order_status(po_id, body.status)
    return {"ok": True}


# ---- drydock_events -------------------------------------------------------------


class DrydockIn(BaseModel):
    yard: str | None = None
    location: str | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    scope_description: str | None = None
    total_cost: float | None = None
    currency: str | None = None


@app.post("/vessels/{name_or_imo}/drydock")
def create_drydock_event(
    name_or_imo: str, body: DrydockIn = DrydockIn(), user: dict | None = Depends(current_user)
):
    authorize(user, "drydock:add")
    vessel = resolve_vessel(name_or_imo)
    fields = body.model_dump(exclude_none=True)
    did = store.add_drydock_event(vessel["id"], coordinated_by=_actor_id(user), **fields)
    return {"id": did}


@app.get("/vessels/{name_or_imo}/drydock")
def list_drydock_events(name_or_imo: str):
    vessel = resolve_vessel(name_or_imo)
    return store.list_drydock_events(vessel["id"])


# ---- safety_incidents (QHSE) --------------------------------------------------


class SafetyIncidentIn(BaseModel):
    incident_type: Literal["near_miss", "incident", "audit", "inspection"]
    description: str
    severity: Literal["low", "medium", "high", "critical"] | None = None


@app.post("/vessels/{name_or_imo}/safety")
def report_safety_incident(
    name_or_imo: str, body: SafetyIncidentIn, user: dict | None = Depends(current_user)
):
    # Deliberately unrestricted — see ops/auth.py's comment on "safety:report".
    vessel = resolve_vessel(name_or_imo)
    fields = body.model_dump(exclude={"incident_type", "description"}, exclude_none=True)
    sid = store.add_safety_incident(
        vessel["id"], body.incident_type, body.description, reported_by=_actor_id(user), **fields
    )
    return {"id": sid}


@app.get("/vessels/{name_or_imo}/safety")
def list_safety_incidents(name_or_imo: str, status: Literal["open", "closed"] | None = None):
    vessel = resolve_vessel(name_or_imo)
    return store.list_safety_incidents(vessel["id"], status=status)


class CloseIncidentIn(BaseModel):
    corrective_action: str | None = None


@app.post("/safety/{incident_id}/close")
def close_safety_incident(
    incident_id: int,
    body: CloseIncidentIn = CloseIncidentIn(),
    user: dict | None = Depends(current_user),
):
    authorize(user, "safety:close")
    store.close_safety_incident(
        incident_id, _actor_id(user), corrective_action=body.corrective_action
    )
    return {"ok": True}
