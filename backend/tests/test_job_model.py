"""Tests for the TaskFlow job model and database setup.

These tests run against an in-memory SQLite database so they do not require a
live PostgreSQL instance. Once a Supabase DATABASE_URL is configured,
integration tests can be added against a real database.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.jobs.models import Job, JobStatus


def test_job_status_enum_values() -> None:
    """Registered job statuses are stable and expected."""
    assert JobStatus.PENDING.value == "pending"
    assert JobStatus.RUNNING.value == "running"
    assert JobStatus.COMPLETED.value == "completed"
    assert JobStatus.FAILED.value == "failed"
    assert JobStatus.CANCELLED.value == "cancelled"


def test_job_model_defaults() -> None:
    """A Job instance defaults to PENDING when flushed (SQLAlchemy applies
    column defaults at flush time, not instantiation)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    job = Job(handler="send_email", payload={"to": "a@example.com"})
    session.add(job)
    session.flush()
    assert job.status == JobStatus.PENDING
    assert job.result is None
    assert job.error is None
    session.close()


def test_job_model_mapped_in_metadata() -> None:
    """The jobs table is registered on SQLAlchemy's declarative metadata."""
    assert "jobs" in Base.metadata.tables
    jobs_table = Base.metadata.tables["jobs"]
    columns = {column.name for column in jobs_table.columns}
    expected = {
        "id",
        "handler",
        "payload",
        "status",
        "result",
        "error",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
    }
    assert expected.issubset(columns)


def test_job_can_be_persisted_to_sqlite() -> None:
    """A Job can be inserted and queried from a SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session: Session = Session(bind=engine)
    job = Job(handler="add_numbers", payload={"a": 2, "b": 3})
    session.add(job)
    session.commit()

    assert job.id is not None

    fetched = session.get(Job, job.id)
    assert fetched is not None
    assert fetched.handler == "add_numbers"
    assert fetched.payload == {"a": 2, "b": 3}
    assert fetched.status == JobStatus.PENDING

    # Transition the job through its lifecycle.
    fetched.status = JobStatus.RUNNING
    fetched.result = {"sum": 5}
    fetched.status = JobStatus.COMPLETED
    session.commit()

    refetched = session.get(Job, job.id)
    assert refetched.status == JobStatus.COMPLETED
    assert refetched.result == {"sum": 5}

    session.close()


def test_job_status_index_exists() -> None:
    """The status and handler columns are indexed for worker lookups."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = __import__("sqlalchemy").inspect(engine)
    indexes = inspector.get_indexes("jobs")
    indexed_columns = {tuple(idx["column_names"]) for idx in indexes}
    assert ("status",) in indexed_columns
    assert ("handler",) in indexed_columns
