import sqlite3
import os
from contextlib import contextmanager

from flask import current_app
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    auth_url TEXT NOT NULL DEFAULT '',
    auth_method TEXT NOT NULL DEFAULT 'password',  -- 'password' or 'application_credential'
    username TEXT NOT NULL DEFAULT '',
    password TEXT NOT NULL DEFAULT '',
    app_cred_id TEXT NOT NULL DEFAULT '',
    app_cred_secret TEXT NOT NULL DEFAULT '',
    project_name TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    user_domain TEXT NOT NULL DEFAULT 'Default',
    project_domain TEXT NOT NULL DEFAULT 'Default',
    region TEXT NOT NULL DEFAULT 'RegionOne',
    verify_ssl INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,           -- 'backup' or 'restore'
    volume_id TEXT,
    volume_name TEXT,
    source_backup_id TEXT,
    dest_backup_id TEXT,
    dest_volume_id TEXT,
    source_cluster_id INTEGER,
    dest_cluster_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, success, failed
    message TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection(db_path=None):
    path = db_path or current_app.config["DATABASE_PATH"]
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_cursor(db_path=None):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Columns added to `tasks` after the initial release, migrated in place so
# existing SQLite files don't error out on "no such column".
_TASKS_MIGRATIONS = [
    ("source_cluster_id", "INTEGER"),
    ("dest_cluster_id", "INTEGER"),
]


def _migrate_columns(conn, table, migrations):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for column, ddl in migrations:
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _migrate_legacy_cluster_config(conn):
    """One-time upgrade path from the old fixed source/destination
    cluster_config table (pre-multi-cluster release) into the new generic
    `clusters` table, so credentials already entered via the old Settings
    page aren't lost. Only runs if `clusters` is still empty and the legacy
    table exists with real (non-blank auth_url) data. The legacy table is
    left in place afterwards, unused, rather than dropped."""
    if not _table_exists(conn, "cluster_config"):
        return
    if conn.execute("SELECT COUNT(*) FROM clusters").fetchone()[0] != 0:
        return

    legacy_cols = {row[1] for row in conn.execute("PRAGMA table_info(cluster_config)")}
    if "auth_url" not in legacy_cols:
        return

    rows = conn.execute("SELECT * FROM cluster_config WHERE auth_url != ''").fetchall()
    for row in rows:
        r = dict(row)
        conn.execute(
            """INSERT INTO clusters
               (name, auth_url, auth_method, username, password, app_cred_id, app_cred_secret,
                project_name, project_id, user_domain, project_domain, region, verify_ssl)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                r.get("name", "Migrated cluster"),
                r.get("auth_url", ""),
                r.get("auth_method", "password"),
                r.get("username", ""),
                r.get("password", ""),
                r.get("app_cred_id", ""),
                r.get("app_cred_secret", ""),
                r.get("project_name", ""),
                r.get("project_id", ""),
                r.get("user_domain", "Default"),
                r.get("project_domain", "Default"),
                r.get("region", "RegionOne"),
                r.get("verify_ssl", 1),
            ),
        )


def init_db(app):
    os.makedirs(os.path.dirname(app.config["DATABASE_PATH"]), exist_ok=True)
    conn = sqlite3.connect(app.config["DATABASE_PATH"])
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        _migrate_columns(conn, "tasks", _TASKS_MIGRATIONS)
        _migrate_legacy_cluster_config(conn)

        cur = conn.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (
                    app.config["DEFAULT_ADMIN_USERNAME"],
                    generate_password_hash(app.config["DEFAULT_ADMIN_PASSWORD"]),
                ),
            )

        conn.commit()
    finally:
        conn.close()


def get_user_by_username(username, db_path=None):
    with db_cursor(db_path) as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


# ----------------------------------------------------------------------
# Clusters (generic — any number, each usable as a backup source and/or
# restore destination)
# ----------------------------------------------------------------------
CLUSTER_FIELDS = [
    "name", "auth_url", "auth_method", "username", "password",
    "app_cred_id", "app_cred_secret", "project_name", "project_id",
    "user_domain", "project_domain", "region", "verify_ssl",
]


def list_clusters():
    with db_cursor() as conn:
        rows = conn.execute("SELECT * FROM clusters ORDER BY name COLLATE NOCASE").fetchall()
        return [dict(r) for r in rows]


def get_cluster(cluster_id):
    with db_cursor() as conn:
        row = conn.execute("SELECT * FROM clusters WHERE id = ?", (cluster_id,)).fetchone()
        return dict(row) if row else None


def create_cluster(**fields):
    columns = [f for f in CLUSTER_FIELDS if f in fields]
    placeholders = ", ".join("?" for _ in columns)
    with db_cursor() as conn:
        cur = conn.execute(
            f"INSERT INTO clusters ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(fields[c] for c in columns),
        )
        return cur.lastrowid


def update_cluster(cluster_id, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    with db_cursor() as conn:
        conn.execute(
            f"UPDATE clusters SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            (*values, cluster_id),
        )


def delete_cluster(cluster_id):
    with db_cursor() as conn:
        conn.execute("DELETE FROM clusters WHERE id = ?", (cluster_id,))


# ----------------------------------------------------------------------
# Tasks (backup / restore history)
# ----------------------------------------------------------------------
def create_task(task_type, volume_id=None, volume_name=None, source_backup_id=None,
                 source_cluster_id=None, dest_cluster_id=None,
                 created_by=None, status="pending", message=None):
    with db_cursor() as conn:
        cur = conn.execute(
            """INSERT INTO tasks (task_type, volume_id, volume_name, source_backup_id,
                                   source_cluster_id, dest_cluster_id,
                                   status, message, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_type, volume_id, volume_name, source_backup_id,
             source_cluster_id, dest_cluster_id, status, message, created_by),
        )
        return cur.lastrowid


def update_task(task_id, **fields):
    if not fields:
        return
    fields_sql = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    with db_cursor() as conn:
        conn.execute(
            f"UPDATE tasks SET {fields_sql}, updated_at = datetime('now') WHERE id = ?",
            (*values, task_id),
        )


_TASKS_SELECT = """
    SELECT t.*,
           sc.name AS source_cluster_name,
           dc.name AS dest_cluster_name
    FROM tasks t
    LEFT JOIN clusters sc ON sc.id = t.source_cluster_id
    LEFT JOIN clusters dc ON dc.id = t.dest_cluster_id
"""


def list_tasks(limit=100):
    with db_cursor() as conn:
        rows = conn.execute(
            f"{_TASKS_SELECT} ORDER BY t.id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_task(task_id):
    with db_cursor() as conn:
        row = conn.execute(f"{_TASKS_SELECT} WHERE t.id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def delete_task(task_id):
    """Removes a task's history row only — does not touch any backup or
    volume that may exist on the actual OpenStack cluster."""
    with db_cursor() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
