"""Create the PostgreSQL/SQLite schema used by ops-dras."""
from alembic import op
import sqlalchemy as sa

revision = "20260730_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("auth_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("auth_method", sa.String(length=32), nullable=False, server_default="password"),
        sa.Column("username", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("password", sa.Text(), nullable=False, server_default=""),
        sa.Column("app_cred_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("app_cred_secret", sa.Text(), nullable=False, server_default=""),
        sa.Column("project_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("user_domain", sa.String(length=255), nullable=False, server_default="Default"),
        sa.Column("project_domain", sa.String(length=255), nullable=False, server_default="Default"),
        sa.Column("region", sa.String(length=255), nullable=False, server_default="RegionOne"),
        sa.Column("verify_ssl", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("volume_id", sa.String(length=255)),
        sa.Column("volume_name", sa.String(length=255)),
        sa.Column("source_backup_id", sa.String(length=255)),
        sa.Column("dest_backup_id", sa.String(length=255)),
        sa.Column("dest_volume_id", sa.String(length=255)),
        sa.Column("source_cluster_id", sa.Integer(), sa.ForeignKey("clusters.id", ondelete="SET NULL")),
        sa.Column("dest_cluster_id", sa.Integer(), sa.ForeignKey("clusters.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("message", sa.Text()),
        sa.Column("created_by", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("tasks")
    op.drop_table("clusters")
    op.drop_table("users")
