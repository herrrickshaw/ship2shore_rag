-- Operations module (Postgres / shore-side). NOT part of the literature RAG
-- corpus in db/schema.sql — this is transactional record-keeping: vessel
-- particulars, crew, logbooks, engineering/maintenance history, fuel. See
-- README "Operations module" for the IAM model and design rationale.
--
-- A SQLite-compatible mirror of this schema lives in ops/store.py for vessel
-- (offline) use — captain's/engine logs and maintenance jobs are created at
-- sea, so they need the same offline-first path the literature corpus has.

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('master', 'chief_engineer', 'officer', 'deck_crew', 'engine_crew', 'shore_staff')),
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vessels (
    id SERIAL PRIMARY KEY,
    imo_number TEXT UNIQUE,
    name TEXT NOT NULL,
    flag TEXT,
    vessel_type TEXT,
    gross_tonnage NUMERIC,
    deadweight NUMERIC,
    build_year INTEGER,
    classification_society TEXT,
    main_engine TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS crew (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER REFERENCES vessels(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    rank TEXT NOT NULL,
    nationality TEXT,
    stcw_cert_number TEXT,
    stcw_cert_expiry DATE,
    sign_on_date DATE,
    sign_off_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS log_entries (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id) ON DELETE CASCADE,
    logged_by INTEGER REFERENCES users(id),
    log_type TEXT NOT NULL CHECK (log_type IN ('deck', 'engine', 'captain')),
    entry_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    latitude NUMERIC,
    longitude NUMERIC,
    entry_text TEXT NOT NULL,
    entry_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', entry_text)) STORED
);
CREATE INDEX IF NOT EXISTS log_entries_tsv_idx ON log_entries USING gin (entry_tsv);
CREATE INDEX IF NOT EXISTS log_entries_vessel_idx ON log_entries (vessel_id, entry_time);

-- EPC (Electronic Parts Catalog) side: engineering asset registry + the
-- parts catalog tied to each asset, matching how shipboard PMS/EPC systems
-- (e.g. ABS Nautical Systems) structure this.
CREATE TABLE IF NOT EXISTS equipment (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    equipment_type TEXT,
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT,
    installed_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS spare_parts (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    part_number TEXT NOT NULL,
    part_name TEXT NOT NULL,
    manufacturer TEXT,
    stock_quantity INTEGER NOT NULL DEFAULT 0,
    unit TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (equipment_id, part_number)
);

CREATE TABLE IF NOT EXISTS maintenance_jobs (
    id SERIAL PRIMARY KEY,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id) ON DELETE CASCADE,
    job_type TEXT NOT NULL CHECK (job_type IN ('scheduled', 'breakdown', 'repair', 'inspection')),
    description TEXT NOT NULL,
    performed_by INTEGER REFERENCES users(id),
    job_date DATE NOT NULL DEFAULT CURRENT_DATE,
    running_hours NUMERIC,
    parts_used TEXT,
    description_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', description)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS maintenance_tsv_idx ON maintenance_jobs USING gin (description_tsv);
CREATE INDEX IF NOT EXISTS maintenance_equipment_idx ON maintenance_jobs (equipment_id, job_date);

CREATE TABLE IF NOT EXISTS fuel_log (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id) ON DELETE CASCADE,
    log_date DATE NOT NULL DEFAULT CURRENT_DATE,
    fuel_type TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('bunkering', 'consumption', 'ROB')),
    quantity_mt NUMERIC NOT NULL,
    rob_after_mt NUMERIC,
    location TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fuel_log_vessel_idx ON fuel_log (vessel_id, log_date);

-- Procurement (purchase-to-pay) — every commercial ship-management platform
-- surveyed (AMOS, ShipNet, BASSnet, DNV ShipManager) treats this as core,
-- tied directly into the spare-parts catalog above.
CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id) ON DELETE CASCADE,
    equipment_id INTEGER REFERENCES equipment(id),
    requested_by INTEGER REFERENCES users(id),
    approved_by INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'approved', 'ordered', 'received', 'cancelled')),
    supplier TEXT,
    items TEXT NOT NULL,
    total_cost NUMERIC,
    currency TEXT,
    order_date DATE,
    expected_delivery DATE,
    received_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS purchase_orders_vessel_idx ON purchase_orders (vessel_id, status);

-- Dry-docking — its own module in every platform surveyed, distinct from
-- routine maintenance_jobs by scale/duration/yard involvement.
CREATE TABLE IF NOT EXISTS drydock_events (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id) ON DELETE CASCADE,
    yard TEXT,
    location TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled')),
    planned_start DATE,
    planned_end DATE,
    actual_start DATE,
    actual_end DATE,
    scope_description TEXT,
    total_cost NUMERIC,
    currency TEXT,
    coordinated_by INTEGER REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS drydock_vessel_idx ON drydock_events (vessel_id, status);

-- QHSE / safety management — near-miss and incident reporting deliberately
-- has NO role restriction to add (see ops/auth.py): a no-blame reporting
-- culture where anyone aboard can report is standard safety-management
-- practice, not an oversight.
CREATE TABLE IF NOT EXISTS safety_incidents (
    id SERIAL PRIMARY KEY,
    vessel_id INTEGER NOT NULL REFERENCES vessels(id) ON DELETE CASCADE,
    incident_type TEXT NOT NULL CHECK (incident_type IN ('near_miss', 'incident', 'audit', 'inspection')),
    severity TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    description TEXT NOT NULL,
    reported_by INTEGER REFERENCES users(id),
    incident_date DATE NOT NULL DEFAULT CURRENT_DATE,
    corrective_action TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    closed_by INTEGER REFERENCES users(id),
    description_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', description)) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS safety_tsv_idx ON safety_incidents USING gin (description_tsv);
CREATE INDEX IF NOT EXISTS safety_vessel_idx ON safety_incidents (vessel_id, status);
