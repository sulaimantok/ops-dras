"""Add persistent task queue, RBAC, structured errors, and audit log."""
from alembic import op
import sqlalchemy as sa

revision = "20260730_02"
down_revision = "20260730_01"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(length=32), nullable=False, server_default="admin"))
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("stage", sa.String(length=32), nullable=False, server_default="queued"))
        batch.add_column(sa.Column("error_code", sa.String(length=64)))
        batch.add_column(sa.Column("error_detail", sa.Text()))
        batch.add_column(sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
        batch.add_column(sa.Column("available_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
        batch.add_column(sa.Column("started_at", sa.DateTime()))
        batch.add_column(sa.Column("finished_at", sa.DateTime()))
        batch.add_column(sa.Column("idempotency_key", sa.String(length=255)))
        batch.create_unique_constraint("uq_tasks_idempotency_key", ["idempotency_key"])
    op.create_index("ix_tasks_queue", "tasks", ["status", "available_at"])
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=255)),
        sa.Column("details", sa.Text()),
        sa.Column("ip_address", sa.String(length=64)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("audit_logs")
    op.drop_index("ix_tasks_queue", table_name="tasks")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("uq_tasks_idempotency_key", type_="unique")
        for column in ("idempotency_key", "finished_at", "started_at", "available_at", "max_attempts", "attempts", "error_detail", "error_code", "stage"):
            batch.drop_column(column)
    with op.batch_alter_table("users") as batch:
        batch.drop_column("role")
