"""Database access layer backed by SQLAlchemy Core.

The same queries run against PostgreSQL (production) and SQLite (legacy
migration/local testing). Schema creation is owned by Alembic, not this file.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import logging
import os

from flask import current_app
from sqlalchemy import create_engine, func, inspect, or_, select, text, update
from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

from app.crypto import CredentialCipher
from app.schema import audit_logs, clusters, tasks, users

logger = logging.getLogger(__name__)

CLUSTER_FIELDS = [
    "name", "auth_url", "auth_method", "username", "password",
    "app_cred_id", "app_cred_secret", "project_name", "project_id",
    "user_domain", "project_domain", "region", "verify_ssl",
]


def _engine():
    return current_app.extensions["ops_dras_db_engine"]


def _credential_cipher(required=False):
    key = current_app.config.get("CLUSTER_CREDENTIALS_KEY", "")
    if not key:
        if required:
            raise ValueError("CLUSTER_CREDENTIALS_KEY must be configured before saving cluster credentials")
        return None
    return CredentialCipher(key)


def _decrypt_cluster(row):
    cluster = dict(row)
    cipher = _credential_cipher()
    if cipher:
        for field in ("password", "app_cred_secret"):
            cluster[field] = cipher.decrypt(cluster[field])
    return cluster


def _encrypt_cluster_fields(fields):
    secret_fields = {field: fields[field] for field in ("password", "app_cred_secret") if field in fields}
    if not any(secret_fields.values()):
        return fields
    cipher = _credential_cipher(required=True)
    encrypted = dict(fields)
    for field, value in secret_fields.items():
        encrypted[field] = cipher.encrypt(value)
    return encrypted


def _database_url(app):
    url = app.config["DATABASE_URL"]
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite" and parsed.database and parsed.database != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(parsed.database)), exist_ok=True)
    return url


def _assert_schema(engine):
    required = {"users", "clusters", "tasks", "audit_logs"}
    existing = set(inspect(engine).get_table_names())
    missing = required - existing
    if missing:
        raise RuntimeError(
            "Database schema is not initialized. Run `alembic upgrade head` before starting ops-dras. "
            f"Missing tables: {', '.join(sorted(missing))}"
        )


def _migrate_cluster_credentials(engine):
    key = current_app.config.get("CLUSTER_CREDENTIALS_KEY", "")
    if not key:
        return
    cipher = CredentialCipher(key)
    with engine.begin() as conn:
        for row in conn.execute(select(clusters.c.id, clusters.c.password, clusters.c.app_cred_secret)).mappings():
            for field in ("password", "app_cred_secret"):
                if row[field] and row[field].startswith("enc:v1:"):
                    cipher.decrypt(row[field])  # fail startup immediately when the configured key is wrong
            values = {
                field: cipher.encrypt(row[field])
                for field in ("password", "app_cred_secret")
                if row[field] and not row[field].startswith("enc:v1:")
            }
            if values:
                conn.execute(update(clusters).where(clusters.c.id == row["id"]).values(**values))


def init_db(app):
    engine = create_engine(_database_url(app), pool_pre_ping=True)
    app.extensions["ops_dras_db_engine"] = engine
    _assert_schema(engine)
    with app.app_context():
        _migrate_cluster_credentials(engine)
        with engine.begin() as conn:
            values = {
                "username": app.config["DEFAULT_ADMIN_USERNAME"],
                "password_hash": generate_password_hash(app.config["DEFAULT_ADMIN_PASSWORD"]),
            }
            # Every Gunicorn worker creates an app instance. Use a native
            # upsert so simultaneous first boots seed one admin safely.
            if engine.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
                statement = insert(users).values(**values).on_conflict_do_nothing(index_elements=[users.c.username])
            elif engine.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
                statement = insert(users).values(**values).on_conflict_do_nothing(index_elements=[users.c.username])
            else:
                statement = users.insert().values(**values)
            conn.execute(statement)


@contextmanager
def db_cursor():
    with _engine().begin() as conn:
        yield conn


def get_user_by_username(username):
    with db_cursor() as conn:
        row = conn.execute(select(users).where(users.c.username == username)).mappings().first()
        return dict(row) if row else None


def list_users():
    with db_cursor() as conn:
        return [dict(row) for row in conn.execute(select(users).order_by(users.c.username)).mappings()]


def create_user(username, password, role="viewer"):
    username = username.strip()
    if not username or len(username) > 255:
        raise ValueError("Username is required and must be 255 characters or fewer")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if role not in {"admin", "operator", "viewer"}:
        raise ValueError("Invalid role")
    with db_cursor() as conn:
        result = conn.execute(users.insert().values(
            username=username, password_hash=generate_password_hash(password), role=role,
        ))
        return result.inserted_primary_key[0]


def update_user_role(username, role):
    if role not in {"admin", "operator", "viewer"}:
        raise ValueError("Invalid role")
    with db_cursor() as conn:
        result = conn.execute(update(users).where(users.c.username == username).values(role=role))
        return result.rowcount == 1


def list_clusters():
    with db_cursor() as conn:
        rows = conn.execute(select(clusters).order_by(clusters.c.name.asc())).mappings()
        return [_decrypt_cluster(row) for row in rows]


def get_cluster(cluster_id):
    with db_cursor() as conn:
        row = conn.execute(select(clusters).where(clusters.c.id == cluster_id)).mappings().first()
        return _decrypt_cluster(row) if row else None


def create_cluster(**fields):
    fields = _encrypt_cluster_fields(fields)
    values = {field: fields[field] for field in CLUSTER_FIELDS if field in fields}
    with db_cursor() as conn:
        result = conn.execute(clusters.insert().values(**values))
        return result.inserted_primary_key[0]


def update_cluster(cluster_id, **fields):
    values = {field: value for field, value in fields.items() if field in CLUSTER_FIELDS}
    if not values:
        return
    values = _encrypt_cluster_fields(values)
    with db_cursor() as conn:
        conn.execute(update(clusters).where(clusters.c.id == cluster_id).values(**values, updated_at=text("CURRENT_TIMESTAMP")))


def delete_cluster(cluster_id):
    with db_cursor() as conn:
        conn.execute(clusters.delete().where(clusters.c.id == cluster_id))


def create_task(task_type, volume_id=None, volume_name=None, source_backup_id=None,
                source_cluster_id=None, dest_cluster_id=None, created_by=None,
                status="queued", message=None, dest_volume_id=None,
                idempotency_key=None, max_attempts=3):
    with db_cursor() as conn:
        if idempotency_key:
            query = select(tasks.c.id, tasks.c.status).where(tasks.c.idempotency_key == idempotency_key)
            if conn.dialect.name == "postgresql":
                query = query.with_for_update()
            existing = conn.execute(query).first()
            if existing and existing.status in {"queued", "running"}:
                return existing.id, False
            if existing:
                conn.execute(update(tasks).where(tasks.c.id == existing.id).values(idempotency_key=None))
        result = conn.execute(tasks.insert().values(
            task_type=task_type, volume_id=volume_id, volume_name=volume_name,
            source_backup_id=source_backup_id, source_cluster_id=source_cluster_id,
            dest_cluster_id=dest_cluster_id, dest_volume_id=dest_volume_id,
            status=status, stage="queued", message=message, created_by=created_by,
            idempotency_key=idempotency_key, max_attempts=max_attempts,
        ))
        return result.inserted_primary_key[0], True


def update_task(task_id, **fields):
    allowed = {column.name for column in tasks.columns} - {"id", "created_at"}
    values = {field: value for field, value in fields.items() if field in allowed}
    if not values:
        return
    with db_cursor() as conn:
        conn.execute(update(tasks).where(tasks.c.id == task_id).values(**values, updated_at=text("CURRENT_TIMESTAMP")))


def _task_query():
    source = clusters.alias("source_cluster")
    destination = clusters.alias("dest_cluster")
    return select(
        tasks,
        source.c.name.label("source_cluster_name"),
        destination.c.name.label("dest_cluster_name"),
    ).outerjoin(source, source.c.id == tasks.c.source_cluster_id).outerjoin(destination, destination.c.id == tasks.c.dest_cluster_id)


def list_tasks(limit=100, offset=0, status=None, task_type=None, search=None):
    query = _task_query()
    if status:
        query = query.where(tasks.c.status == status)
    if task_type:
        query = query.where(tasks.c.task_type == task_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(tasks.c.volume_name.ilike(pattern), tasks.c.volume_id.ilike(pattern), tasks.c.message.ilike(pattern)))
    with db_cursor() as conn:
        rows = conn.execute(query.order_by(tasks.c.id.desc()).limit(limit).offset(offset)).mappings()
        return [dict(row) for row in rows]


def count_tasks(status=None, task_type=None, search=None):
    query = select(func.count()).select_from(tasks)
    if status:
        query = query.where(tasks.c.status == status)
    if task_type:
        query = query.where(tasks.c.task_type == task_type)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(tasks.c.volume_name.ilike(pattern), tasks.c.volume_id.ilike(pattern), tasks.c.message.ilike(pattern)))
    with db_cursor() as conn:
        return conn.execute(query).scalar_one()


def dashboard_stats():
    with db_cursor() as conn:
        cluster_count = conn.execute(select(func.count()).select_from(clusters)).scalar_one()
        status_rows = conn.execute(select(tasks.c.status, func.count()).group_by(tasks.c.status)).all()
        last_restore = conn.execute(
            select(tasks).where(tasks.c.task_type == "restore").order_by(tasks.c.id.desc()).limit(1)
        ).mappings().first()
        return {
            "clusters": cluster_count,
            "statuses": dict(status_rows),
            "last_restore": dict(last_restore) if last_restore else None,
        }


def get_task(task_id):
    with db_cursor() as conn:
        row = conn.execute(_task_query().where(tasks.c.id == task_id)).mappings().first()
        return dict(row) if row else None


def delete_task(task_id):
    """Remove history only; no real Cinder backup or volume is deleted."""
    with db_cursor() as conn:
        conn.execute(tasks.delete().where(tasks.c.id == task_id))


def cancel_task(task_id):
    with db_cursor() as conn:
        result = conn.execute(
            update(tasks).where(tasks.c.id == task_id, tasks.c.status == "queued").values(
                status="cancelled", stage="cancelled", message="Cancelled by operator",
                finished_at=text("CURRENT_TIMESTAMP"), updated_at=text("CURRENT_TIMESTAMP"),
            )
        )
        return result.rowcount == 1


def claim_next_task():
    """Atomically claim one queued task; PostgreSQL workers use SKIP LOCKED."""
    with db_cursor() as conn:
        query = (
            select(tasks)
            .where(tasks.c.status == "queued", tasks.c.available_at <= text("CURRENT_TIMESTAMP"))
            .order_by(tasks.c.id.asc())
            .limit(1)
        )
        if conn.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        row = conn.execute(query).mappings().first()
        if not row:
            return None
        claimed = conn.execute(
            update(tasks)
            .where(tasks.c.id == row["id"], tasks.c.status == "queued")
            .values(
                status="running", stage="running", attempts=tasks.c.attempts + 1,
                started_at=text("COALESCE(started_at, CURRENT_TIMESTAMP)"),
                updated_at=text("CURRENT_TIMESTAMP"),
            )
        )
        if claimed.rowcount != 1:
            return None
        return dict(conn.execute(select(tasks).where(tasks.c.id == row["id"])).mappings().one())


def retry_task(task_id, message, error_code=None, error_detail=None, delay_seconds=5):
    with db_cursor() as conn:
        dialect = conn.dialect.name
        if dialect == "postgresql":
            available_at = text(f"CURRENT_TIMESTAMP + INTERVAL '{int(delay_seconds)} seconds'")
        else:
            available_at = text(f"datetime(CURRENT_TIMESTAMP, '+{int(delay_seconds)} seconds')")
        conn.execute(
            update(tasks).where(tasks.c.id == task_id).values(
                status="queued", stage="queued", message=message,
                error_code=error_code, error_detail=error_detail,
                available_at=available_at, updated_at=text("CURRENT_TIMESTAMP"),
            )
        )


def recover_interrupted_tasks():
    with db_cursor() as conn:
        result = conn.execute(
            update(tasks).where(tasks.c.status == "running").values(
                status="queued", stage="queued", message="Recovered after worker restart",
                available_at=text("CURRENT_TIMESTAMP"), updated_at=text("CURRENT_TIMESTAMP"),
            )
        )
        return result.rowcount


def has_active_tasks_for_cluster(cluster_id):
    with db_cursor() as conn:
        row = conn.execute(
            select(tasks.c.id).where(
                tasks.c.status.in_(["queued", "running"]),
                (tasks.c.source_cluster_id == cluster_id) | (tasks.c.dest_cluster_id == cluster_id),
            ).limit(1)
        ).first()
        return row is not None


def create_audit_log(actor, action, resource_type, resource_id=None, details=None, ip_address=None):
    with db_cursor() as conn:
        conn.execute(audit_logs.insert().values(
            actor=actor or "system", action=action, resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details, ip_address=ip_address,
        ))


def list_audit_logs(limit=200):
    with db_cursor() as conn:
        return [dict(row) for row in conn.execute(
            select(audit_logs).order_by(audit_logs.c.id.desc()).limit(limit)
        ).mappings()]


def count_recent_login_failures(ip_address, window_seconds):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=window_seconds)
    with db_cursor() as conn:
        return len(conn.execute(
            select(audit_logs.c.id).where(
                audit_logs.c.action == "login.failed",
                audit_logs.c.ip_address == ip_address,
                audit_logs.c.created_at >= cutoff,
            )
        ).all())


def ping():
    with db_cursor() as conn:
        conn.execute(text("SELECT 1"))
