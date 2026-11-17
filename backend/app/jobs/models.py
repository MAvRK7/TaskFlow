"""TaskFlow job models.

The :class:`Job` table is the single source of truth for a background job's
lifecycle: submission, execution, and result retrieval.

Responsibilities (kept separate from API, queue, and worker layers):
- Persist job state in PostgreSQL via SQLAlchemy 2.0.
- Expose a small set of status transitions used by the API and workers.

Notes on column behaviour:

* ``updated_at`` — ``server_default=func.now()`` sets the value on INSERT at
  the database level. ``onupdate=func.now()`` is ORM-side only: it fires when
  the instance is flushed through SQLAlchemy's unit of work, but it does NOT
  fire for raw SQL UPDATEs, bulk updates (``query.update()``), or updates
  made by other services. For a database-level ``updated_at`` that updates on
  every write, a PostgreSQL trigger would be required.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class JobStatus(str, PyEnum):
    """Registered job lifecycle statuses."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# JSON type that maps to PostgreSQL JSONB on Postgres and plain JSON on
# SQLite (used by the test suite).
_json_type = JSON().with_variant(JSONB(), "postgresql")


class Job(Base):
    """A single background job.

    Attributes:
        id: Server-generated UUID primary key.
        handler: Name of the registered job handler that should execute the
            job. Workers look up handlers by name from a registry; arbitrary
            user-supplied code is never executed.
        payload: JSON-serialisable input data for the handler. Non-nullable;
            defaults to an empty object.
        status: Current lifecycle status. Defaults to ``pending`` at both the
            ORM and database levels.
        result: JSON-serialisable output produced by the handler (nullable).
        error: Error message if the job failed (nullable).
        created_at: Timestamp when the job was inserted (database default).
        updated_at: Timestamp automatically refreshed on ORM flush (see notes
            above for limitations).
        started_at: Timestamp when a worker picked the job up (nullable).
        completed_at: Timestamp when the job reached a terminal state
            (nullable).
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, nullable=False
    )
    handler: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        _json_type,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=JobStatus.PENDING,
        server_default="pending",
        index=True,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(_json_type, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<Job(id={self.id}, handler={self.handler!r}, status={self.status.value})>"
        )


__all__ = ["Job", "JobStatus"]
