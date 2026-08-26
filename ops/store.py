"""Operations data store — vessels, crew, logbooks, engineering/EPC records,
fuel. Dispatches on config.STORAGE_BACKEND, same switch the literature
retrieval path uses: Postgres shore-side, SQLite vessel-side (offline, no
server — captain's/engine logs and maintenance jobs are recorded at sea, so
this needs the same offline-first path as everything else in this project).

Kept deliberately simple: generic insert/list helpers parameterized by table
name, plus a thin higher-level function per entity for readability. No ORM —
this is a handful of tables for a single-vessel-scale tool, not a reason to
add a dependency.
"""

import sqlite3

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL, OPS_SQLITE_PATH, STORAGE_BACKEND

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vessels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    imo_number TEXT UNIQUE,
    name TEXT NOT NULL,
    flag TEXT,
    vessel_type TEXT,
    gross_tonnage REAL,
    deadweight REAL,
    build_year INTEGER,
    classification_society TEXT,
    main_engine TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS crew (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id INTEGER REFERENCES vessels(id),
    name TEXT NOT NULL,
    rank TEXT NOT NULL,
    nationality TEXT,
    stcw_cert_number TEXT,
    stcw_cert_expiry TEXT,
    sign_on_date TEXT,
    sign_off_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS log_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id),
    logged_by INTEGER REFERENCES users(id),
    log_type TEXT NOT NULL,
    entry_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    latitude REAL,
    longitude REAL,
    entry_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id),
    name TEXT NOT NULL,
    equipment_type TEXT,
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT,
    installed_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS spare_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id),
    part_number TEXT NOT NULL,
    part_name TEXT NOT NULL,
    manufacturer TEXT,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    unit TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (equipment_id, part_number)
);

CREATE TABLE IF NOT EXISTS maintenance_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id),
    job_type TEXT NOT NULL,
    description TEXT NOT NULL,
    performed_by INTEGER REFERENCES users(id),
    job_date TEXT NOT NULL DEFAULT CURRENT_DATE,
    running_hours REAL,
    parts_used TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fuel_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id),
    log_date TEXT NOT NULL DEFAULT CURRENT_DATE,
    fuel_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    quantity_mt REAL NOT NULL,
    rob_after_mt REAL,
    location TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id),
    equipment_id INTEGER REFERENCES equipment(id),
    requested_by INTEGER REFERENCES users(id),
    approved_by INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'requested',
    supplier TEXT,
    items TEXT NOT NULL,
    total_cost REAL,
    currency TEXT,
    order_date TEXT,
    expected_delivery TEXT,
    received_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drydock_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id),
    yard TEXT,
    location TEXT,
    status TEXT NOT NULL DEFAULT 'planned',
    planned_start TEXT,
    planned_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    scope_description TEXT,
    total_cost REAL,
    currency TEXT,
    coordinated_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS safety_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id),
    incident_type TEXT NOT NULL,
    severity TEXT,
    description TEXT NOT NULL,
    reported_by INTEGER REFERENCES users(id),
    incident_date TEXT NOT NULL DEFAULT CURRENT_DATE,
    corrective_action TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    closed_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _sqlite_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(OPS_SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SQLITE_SCHEMA)
    return conn


class _Conn:
    """Wraps either a psycopg or sqlite3 connection behind one interface:
    .execute(sql_pg, sql_lite, params) -> cursor-like with .fetchall()/.fetchone(),
    using whichever SQL dialect matches the active backend."""

    def __init__(self):
        self.backend = STORAGE_BACKEND
        if self.backend == "sqlite":
            self.conn = _sqlite_connect()
        else:
            self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    def execute(self, pg_sql: str, lite_sql: str, params: tuple = ()):
        sql = lite_sql if self.backend == "sqlite" else pg_sql
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if exc[0] is None:
            self.commit()
        self.close()


def _rows(cur, backend: str) -> list[dict]:
    if backend == "sqlite":
        return [dict(r) for r in cur.fetchall()]
    return cur.fetchall()  # dict_row already gives dicts


def _row(cur, backend: str) -> dict | None:
    r = cur.fetchone()
    if r is None:
        return None
    return dict(r) if backend == "sqlite" else r


# ---- users ----------------------------------------------------------------


def add_user(name: str, role: str, email: str | None = None) -> int:
    with _Conn() as c:
        cur = c.execute(
            "INSERT INTO users (name, role, email) VALUES (%s, %s, %s) RETURNING id",
            "INSERT INTO users (name, role, email) VALUES (?, ?, ?)",
            (name, role, email),
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def get_user_by_name(name: str) -> dict | None:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM users WHERE name = %s", "SELECT * FROM users WHERE name = ?", (name,)
        )
        return _row(cur, c.backend)


def list_users() -> list[dict]:
    with _Conn() as c:
        cur = c.execute("SELECT * FROM users ORDER BY name", "SELECT * FROM users ORDER BY name")
        return _rows(cur, c.backend)


# ---- vessels ----------------------------------------------------------------


def add_vessel(name: str, imo_number: str | None = None, **fields) -> int:
    cols = ["name", "imo_number", *fields.keys()]
    vals = (name, imo_number, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO vessels ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO vessels ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_vessels() -> list[dict]:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM vessels ORDER BY name", "SELECT * FROM vessels ORDER BY name"
        )
        return _rows(cur, c.backend)


def get_vessel(name_or_imo: str) -> dict | None:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM vessels WHERE name = %s OR imo_number = %s",
            "SELECT * FROM vessels WHERE name = ? OR imo_number = ?",
            (name_or_imo, name_or_imo),
        )
        return _row(cur, c.backend)


# ---- crew (seafarer onboarding) --------------------------------------------


def add_crew(name: str, rank: str, vessel_id: int | None = None, **fields) -> int:
    cols = ["name", "rank", "vessel_id", *fields.keys()]
    vals = (name, rank, vessel_id, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO crew ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO crew ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_crew(vessel_id: int | None = None) -> list[dict]:
    with _Conn() as c:
        if vessel_id is not None:
            cur = c.execute(
                "SELECT * FROM crew WHERE vessel_id = %s ORDER BY sign_on_date",
                "SELECT * FROM crew WHERE vessel_id = ? ORDER BY sign_on_date",
                (vessel_id,),
            )
        else:
            cur = c.execute("SELECT * FROM crew ORDER BY name", "SELECT * FROM crew ORDER BY name")
        return _rows(cur, c.backend)


def crew_signoff(crew_id: int, sign_off_date: str) -> None:
    with _Conn() as c:
        c.execute(
            "UPDATE crew SET sign_off_date = %s WHERE id = %s",
            "UPDATE crew SET sign_off_date = ? WHERE id = ?",
            (sign_off_date, crew_id),
        )


# ---- log_entries (master/captain/deck/engine log) --------------------------


def add_log_entry(
    vessel_id: int, log_type: str, entry_text: str, logged_by: int | None = None, **fields
) -> int:
    cols = ["vessel_id", "log_type", "entry_text", "logged_by", *fields.keys()]
    vals = (vessel_id, log_type, entry_text, logged_by, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO log_entries ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO log_entries ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_log_entries(vessel_id: int, log_type: str | None = None) -> list[dict]:
    with _Conn() as c:
        if log_type:
            cur = c.execute(
                "SELECT * FROM log_entries WHERE vessel_id = %s AND log_type = %s ORDER BY entry_time DESC",
                "SELECT * FROM log_entries WHERE vessel_id = ? AND log_type = ? ORDER BY entry_time DESC",
                (vessel_id, log_type),
            )
        else:
            cur = c.execute(
                "SELECT * FROM log_entries WHERE vessel_id = %s ORDER BY entry_time DESC",
                "SELECT * FROM log_entries WHERE vessel_id = ? ORDER BY entry_time DESC",
                (vessel_id,),
            )
        return _rows(cur, c.backend)


# ---- equipment / EPC (spare parts) / maintenance ---------------------------


def add_equipment(vessel_id: int, name: str, **fields) -> int:
    cols = ["vessel_id", "name", *fields.keys()]
    vals = (vessel_id, name, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO equipment ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO equipment ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_equipment(vessel_id: int) -> list[dict]:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM equipment WHERE vessel_id = %s ORDER BY name",
            "SELECT * FROM equipment WHERE vessel_id = ? ORDER BY name",
            (vessel_id,),
        )
        return _rows(cur, c.backend)


def add_part(equipment_id: int, part_number: str, part_name: str, **fields) -> int:
    cols = ["equipment_id", "part_number", "part_name", *fields.keys()]
    vals = (equipment_id, part_number, part_name, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO spare_parts ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO spare_parts ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_parts(equipment_id: int) -> list[dict]:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM spare_parts WHERE equipment_id = %s ORDER BY part_number",
            "SELECT * FROM spare_parts WHERE equipment_id = ? ORDER BY part_number",
            (equipment_id,),
        )
        return _rows(cur, c.backend)


def add_maintenance(
    equipment_id: int, job_type: str, description: str, performed_by: int | None = None, **fields
) -> int:
    cols = ["equipment_id", "job_type", "description", "performed_by", *fields.keys()]
    vals = (equipment_id, job_type, description, performed_by, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO maintenance_jobs ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO maintenance_jobs ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_maintenance(equipment_id: int) -> list[dict]:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM maintenance_jobs WHERE equipment_id = %s ORDER BY job_date DESC",
            "SELECT * FROM maintenance_jobs WHERE equipment_id = ? ORDER BY job_date DESC",
            (equipment_id,),
        )
        return _rows(cur, c.backend)


# ---- fuel_log ---------------------------------------------------------------


def add_fuel_entry(
    vessel_id: int, fuel_type: str, event_type: str, quantity_mt: float, **fields
) -> int:
    cols = ["vessel_id", "fuel_type", "event_type", "quantity_mt", *fields.keys()]
    vals = (vessel_id, fuel_type, event_type, quantity_mt, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO fuel_log ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO fuel_log ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_fuel_log(vessel_id: int) -> list[dict]:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM fuel_log WHERE vessel_id = %s ORDER BY log_date DESC",
            "SELECT * FROM fuel_log WHERE vessel_id = ? ORDER BY log_date DESC",
            (vessel_id,),
        )
        return _rows(cur, c.backend)


# ---- purchase_orders (procurement) -----------------------------------------


def add_purchase_order(
    vessel_id: int, items: str, requested_by: int | None = None, **fields
) -> int:
    cols = ["vessel_id", "items", "requested_by", *fields.keys()]
    vals = (vessel_id, items, requested_by, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO purchase_orders ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO purchase_orders ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_purchase_orders(vessel_id: int, status: str | None = None) -> list[dict]:
    with _Conn() as c:
        if status:
            cur = c.execute(
                "SELECT * FROM purchase_orders WHERE vessel_id = %s AND status = %s ORDER BY created_at DESC",
                "SELECT * FROM purchase_orders WHERE vessel_id = ? AND status = ? ORDER BY created_at DESC",
                (vessel_id, status),
            )
        else:
            cur = c.execute(
                "SELECT * FROM purchase_orders WHERE vessel_id = %s ORDER BY created_at DESC",
                "SELECT * FROM purchase_orders WHERE vessel_id = ? ORDER BY created_at DESC",
                (vessel_id,),
            )
        return _rows(cur, c.backend)


def approve_purchase_order(po_id: int, approved_by: int | None) -> None:
    with _Conn() as c:
        c.execute(
            "UPDATE purchase_orders SET status = 'approved', approved_by = %s WHERE id = %s",
            "UPDATE purchase_orders SET status = 'approved', approved_by = ? WHERE id = ?",
            (approved_by, po_id),
        )


def update_purchase_order_status(po_id: int, status: str) -> None:
    with _Conn() as c:
        c.execute(
            "UPDATE purchase_orders SET status = %s WHERE id = %s",
            "UPDATE purchase_orders SET status = ? WHERE id = ?",
            (status, po_id),
        )


# ---- drydock_events ---------------------------------------------------------


def add_drydock_event(vessel_id: int, **fields) -> int:
    cols = ["vessel_id", *fields.keys()]
    vals = (vessel_id, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO drydock_events ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO drydock_events ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_drydock_events(vessel_id: int) -> list[dict]:
    with _Conn() as c:
        cur = c.execute(
            "SELECT * FROM drydock_events WHERE vessel_id = %s ORDER BY planned_start DESC",
            "SELECT * FROM drydock_events WHERE vessel_id = ? ORDER BY planned_start DESC",
            (vessel_id,),
        )
        return _rows(cur, c.backend)


# ---- safety_incidents (QHSE) ------------------------------------------------


def add_safety_incident(
    vessel_id: int, incident_type: str, description: str, reported_by: int | None = None, **fields
) -> int:
    cols = ["vessel_id", "incident_type", "description", "reported_by", *fields.keys()]
    vals = (vessel_id, incident_type, description, reported_by, *fields.values())
    placeholders_pg = ", ".join(["%s"] * len(cols))
    placeholders_lite = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    with _Conn() as c:
        cur = c.execute(
            f"INSERT INTO safety_incidents ({col_list}) VALUES ({placeholders_pg}) RETURNING id",
            f"INSERT INTO safety_incidents ({col_list}) VALUES ({placeholders_lite})",
            vals,
        )
        return cur.fetchone()["id"] if c.backend != "sqlite" else cur.lastrowid


def list_safety_incidents(vessel_id: int, status: str | None = None) -> list[dict]:
    with _Conn() as c:
        if status:
            cur = c.execute(
                "SELECT * FROM safety_incidents WHERE vessel_id = %s AND status = %s ORDER BY incident_date DESC",
                "SELECT * FROM safety_incidents WHERE vessel_id = ? AND status = ? ORDER BY incident_date DESC",
                (vessel_id, status),
            )
        else:
            cur = c.execute(
                "SELECT * FROM safety_incidents WHERE vessel_id = %s ORDER BY incident_date DESC",
                "SELECT * FROM safety_incidents WHERE vessel_id = ? ORDER BY incident_date DESC",
                (vessel_id,),
            )
        return _rows(cur, c.backend)


def close_safety_incident(
    incident_id: int, closed_by: int | None, corrective_action: str | None = None
) -> None:
    with _Conn() as c:
        c.execute(
            "UPDATE safety_incidents SET status = 'closed', closed_by = %s, corrective_action = COALESCE(%s, corrective_action) WHERE id = %s",
            "UPDATE safety_incidents SET status = 'closed', closed_by = ?, corrective_action = COALESCE(?, corrective_action) WHERE id = ?",
            (closed_by, corrective_action, incident_id),
        )
