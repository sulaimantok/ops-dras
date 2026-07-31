"""Database schema shared by the application and Alembic migrations."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, func

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(255), nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("role", String(32), nullable=False, server_default="admin"),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)

clusters = Table(
    "clusters", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("auth_url", Text, nullable=False, server_default=""),
    Column("auth_method", String(32), nullable=False, server_default="password"),
    Column("username", String(255), nullable=False, server_default=""),
    Column("password", Text, nullable=False, server_default=""),
    Column("app_cred_id", String(255), nullable=False, server_default=""),
    Column("app_cred_secret", Text, nullable=False, server_default=""),
    Column("project_name", String(255), nullable=False, server_default=""),
    Column("project_id", String(255), nullable=False, server_default=""),
    Column("user_domain", String(255), nullable=False, server_default="Default"),
    Column("project_domain", String(255), nullable=False, server_default="Default"),
    Column("region", String(255), nullable=False, server_default="RegionOne"),
    Column("verify_ssl", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
)

tasks = Table(
    "tasks", metadata,
    Column("id", Integer, primary_key=True),
    Column("task_type", String(32), nullable=False),
    Column("volume_id", String(255)),
    Column("volume_name", String(255)),
    Column("source_backup_id", String(255)),
    Column("backup_mode", String(32), nullable=False, server_default="full"),
    Column("is_incremental", Boolean),
    Column("parent_backup_id", String(255)),
    Column("dest_backup_id", String(255)),
    Column("dest_volume_id", String(255)),
    Column("source_cluster_id", Integer, ForeignKey("clusters.id", ondelete="SET NULL")),
    Column("dest_cluster_id", Integer, ForeignKey("clusters.id", ondelete="SET NULL")),
    Column("status", String(32), nullable=False, server_default="pending"),
    Column("stage", String(32), nullable=False, server_default="queued"),
    Column("message", Text),
    Column("error_code", String(64)),
    Column("error_detail", Text),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("max_attempts", Integer, nullable=False, server_default="3"),
    Column("available_at", DateTime, nullable=False, server_default=func.now()),
    Column("started_at", DateTime),
    Column("finished_at", DateTime),
    Column("idempotency_key", String(255), unique=True),
    Column("created_by", String(255)),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
)

audit_logs = Table(
    "audit_logs", metadata,
    Column("id", Integer, primary_key=True),
    Column("actor", String(255), nullable=False),
    Column("action", String(64), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("resource_id", String(255)),
    Column("details", Text),
    Column("ip_address", String(64)),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
)
