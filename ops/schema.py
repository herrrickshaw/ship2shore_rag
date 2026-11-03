"""SQLite DDL for the operations store (vessel-side, offline backend)."""

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
