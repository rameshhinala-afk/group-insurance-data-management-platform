"""Database layer: schema + connection helper (SQLite, standard library only)."""
import os
import sqlite3

DB_PATH = os.getenv("INSURANCE_DB", "insurance.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    group_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    industry      TEXT,
    contact_email TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT NOT NULL UNIQUE,
    sum_insured             REAL NOT NULL CHECK (sum_insured > 0),
    monthly_premium_per_member REAL NOT NULL CHECK (monthly_premium_per_member > 0)
);

CREATE TABLE IF NOT EXISTS policies (
    policy_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id   INTEGER NOT NULL REFERENCES groups(group_id),
    plan_id    INTEGER NOT NULL REFERENCES plans(plan_id),
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','cancelled'))
);

CREATE TABLE IF NOT EXISTS members (
    member_id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id  INTEGER NOT NULL REFERENCES groups(group_id),
    name      TEXT NOT NULL,
    dob       TEXT NOT NULL,
    relation  TEXT NOT NULL DEFAULT 'self',
    email     TEXT,
    status    TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    UNIQUE (group_id, name, dob)
);

CREATE TABLE IF NOT EXISTS premiums (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id  INTEGER NOT NULL REFERENCES policies(policy_id),
    amount     REAL NOT NULL CHECK (amount > 0),
    paid_date  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claims (
    claim_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id   INTEGER NOT NULL REFERENCES policies(policy_id),
    member_id   INTEGER NOT NULL REFERENCES members(member_id),
    amount      REAL NOT NULL CHECK (amount > 0),
    claim_date  TEXT NOT NULL,
    description TEXT,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    decision_note TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    action     TEXT NOT NULL,
    entity     TEXT NOT NULL,
    entity_id  INTEGER,
    details    TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_members_group ON members(group_id);
CREATE INDEX IF NOT EXISTS idx_claims_policy ON claims(policy_id);
"""


def get_conn(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
