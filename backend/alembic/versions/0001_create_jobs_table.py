"""Create jobs table

Revision ID: 0001_create_jobs_table
Revises:
Create Date: 2026-11-17 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_create_jobs_table"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Explicitly public: Alembic reads these identifiers by name via module
# introspection. Declared in __all__ so code-scanning tools do not flag
# them as unused globals.
__all__ = ["branch_labels", "depends_on", "down_revision", "revision"]


def upgrade() -> None:
    # Create the PostgreSQL native enum type. The DO block makes the
    # migration idempotent: re-running it does not raise a duplicate-type
    # error if the enum already exists.
    op.execute(
        "DO $$ BEGIN "
        "    CREATE TYPE jobstatus AS ENUM "
        "    ('pending', 'running', 'completed', 'failed', 'cancelled'); "
        "EXCEPTION "
        "    WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    op.create_table(
        "jobs",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column("handler", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="jobstatus",
                values_callable=lambda x: [e.value for e in x],
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "result",
            sa.dialects.postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_jobs_handler"), "jobs", ["handler"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_handler"), table_name="jobs")
    op.drop_table("jobs")
    # DROP TYPE IF EXISTS is supported on PostgreSQL 9.2+ (Supabase included).
    op.execute("DROP TYPE IF EXISTS jobstatus;")
