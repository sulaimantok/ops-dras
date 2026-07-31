"""Add incremental Cinder backup metadata to tasks."""
from alembic import op
import sqlalchemy as sa

revision = "20260731_03"
down_revision = "20260730_02"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("backup_mode", sa.String(length=32), nullable=False, server_default="full"))
        batch.add_column(sa.Column("is_incremental", sa.Boolean()))
        batch.add_column(sa.Column("parent_backup_id", sa.String(length=255)))


def downgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("parent_backup_id")
        batch.drop_column("is_incremental")
        batch.drop_column("backup_mode")
