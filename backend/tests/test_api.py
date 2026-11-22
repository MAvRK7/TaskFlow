"""Tests for the TaskFlow job API routes.

Tests run against an in-memory SQLite database by overriding the
``get_db`` dependency, so no live PostgreSQL instance is required.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.jobs.models import Job
from app.jobs.schemas import MAX_PAYLOAD_BYTES
from app.main import app
from app.queue.client import get_queue

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


class FakeQueue:
    """In-memory fake queue for testing: records enqueued job IDs."""

    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)

    def dequeue(self, timeout: float) -> str | None:
        return None

    def close(self) -> None:
        pass


class CommitFailingSession:
    """Session proxy whose ``commit`` fails once ``allowed_commits`` is used up.

    Stands in for a database that goes away between the first job commit and
    the recovery write that records the enqueue failure.
    """

    def __init__(self, session: Session, allowed_commits: int = 1) -> None:
        self._session = session
        self._remaining = allowed_commits

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def commit(self) -> None:
        if self._remaining <= 0:
            raise RuntimeError("database is gone")
        self._remaining -= 1
        self._session.commit()


def _job_count() -> int:
    """Return the number of job rows, using the SQLAlchemy 2.0 API."""
    with Session(bind=_TEST_ENGINE) as session:
        return session.scalar(select(func.count()).select_from(Job)) or 0


def _only_job() -> Job:
    """Return the single job row, detached after its values are loaded."""
    with Session(bind=_TEST_ENGINE) as session:
        job = session.scalars(select(Job)).one()
        session.expunge(job)
        return job


@pytest.fixture(autouse=True)
def setup_database() -> Iterator[None]:
    """Create all tables before each test and drop them after.

    Ensures each test starts with a clean database and no leftover rows
    from previous tests can cause interference.
    """
    Base.metadata.create_all(_TEST_ENGINE)
    yield
    Base.metadata.drop_all(_TEST_ENGINE)


@pytest.fixture
def queue() -> FakeQueue:
    """Provide a fake queue that records enqueued job IDs."""
    return FakeQueue()


def _override_get_db() -> Iterator[Session]:
    """Yield a session bound to the shared in-memory test engine."""
    session = Session(bind=_TEST_ENGINE)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(queue: FakeQueue) -> Iterator[TestClient]:
    """Provide a TestClient with ``get_db`` and ``get_queue`` overridden.

    Overrides are cleared after the test so other test modules that import
    ``app`` are not affected.
    """
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_queue] = lambda: queue
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_queue, None)


def test_create_job_returns_201_and_job_fields(
    client: TestClient, queue: FakeQueue
) -> None:
    """POST /jobs creates a pending job and returns its fields."""
    response = client.post(
        "/jobs",
        json={"handler": "echo", "payload": {"to": "a@example.com"}},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["handler"] == "echo"
    assert body["payload"] == {"to": "a@example.com"}
    assert body["status"] == "pending"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body
    assert queue.enqueued == [body["id"]]


def test_create_job_defaults_payload_to_empty_object(
    client: TestClient, queue: FakeQueue
) -> None:
    """POST /jobs without payload stores an empty object."""
    response = client.post("/jobs", json={"handler": "add_numbers"})
    assert response.status_code == 201, response.text
    assert response.json()["payload"] == {}


def test_create_job_missing_handler_returns_422(
    client: TestClient, queue: FakeQueue
) -> None:
    """POST /jobs without a handler returns 422 for invalid input."""
    response = client.post("/jobs", json={"payload": {"to": "a@example.com"}})
    assert response.status_code == 422, response.text


def test_create_job_invalid_payload_type_returns_422(
    client: TestClient, queue: FakeQueue
) -> None:
    """POST /jobs with a non-object payload returns 422."""
    response = client.post("/jobs", json={"handler": "echo", "payload": "not-a-dict"})
    assert response.status_code == 422, response.text


def test_create_job_handler_too_long_returns_422(
    client: TestClient, queue: FakeQueue
) -> None:
    """POST /jobs with a handler longer than the DB column (255) returns 422.

    Asserts on the validation error location and type so the test cannot also
    pass because of registry rejection (an unknown handler is rejected with a
    plain string detail, not a pydantic error list).
    """
    response = client.post("/jobs", json={"handler": "h" * 256})
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "handler"]
    assert detail[0]["type"] == "string_too_long"
    assert queue.enqueued == []


def test_create_job_payload_at_limit_is_accepted(
    client: TestClient, queue: FakeQueue
) -> None:
    """A payload just under the size cap is accepted."""
    payload = {"blob": "x" * (MAX_PAYLOAD_BYTES - 32)}
    response = client.post("/jobs", json={"handler": "echo", "payload": payload})
    assert response.status_code == 201, response.text
    assert len(queue.enqueued) == 1


def test_create_job_payload_too_large_returns_422(
    client: TestClient, queue: FakeQueue
) -> None:
    """An oversized JSON payload is rejected at the API boundary."""
    payload = {"blob": "x" * MAX_PAYLOAD_BYTES}
    response = client.post("/jobs", json={"handler": "echo", "payload": payload})
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "payload"]
    assert queue.enqueued == []
    assert _job_count() == 0


def test_create_job_unregistered_handler_returns_422(
    client: TestClient, queue: FakeQueue
) -> None:
    """POST /jobs with an unregistered handler returns 422, no row, no queue entry."""
    response = client.post(
        "/jobs", json={"handler": "nonexistent_handler", "payload": {}}
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert "nonexistent_handler" in body["detail"]
    assert "echo" in body["detail"]
    assert "add_numbers" in body["detail"]
    assert queue.enqueued == []
    assert _job_count() == 0


def test_create_job_enqueue_failure_returns_503_and_marks_failed(
    client: TestClient, queue: FakeQueue
) -> None:
    """An enqueue failure returns 503 and leaves a terminal, diagnosable job.

    The cause is recorded (exception type and message), ``completed_at`` is set
    because ``failed`` is terminal, and nothing is left in the queue.
    """
    attempts: list[str] = []

    def failing_enqueue(job_id: str) -> None:
        attempts.append(job_id)
        raise RuntimeError("Redis is down")

    queue.enqueue = failing_enqueue  # type: ignore[method-assign]

    response = client.post("/jobs", json={"handler": "echo", "payload": {}})
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Job created but could not be queued"
    assert len(attempts) == 1
    assert queue.enqueued == []

    job = _only_job()
    assert job.status == "failed"
    assert job.error == "RuntimeError: Redis is down"
    assert job.completed_at is not None


def test_create_job_returns_503_when_recovery_write_fails(
    client: TestClient, queue: FakeQueue, caplog: pytest.LogCaptureFixture
) -> None:
    """A failing recovery write still yields 503, and the job id is logged.

    The row is documented to stay ``pending`` in this case (Phase 3 known
    limitation); what must not happen is a 500 or a silently unlogged row.
    """
    caplog.set_level(logging.ERROR)

    def failing_enqueue(job_id: str) -> None:
        raise RuntimeError("Redis is down")

    queue.enqueue = failing_enqueue  # type: ignore[method-assign]

    def _override_get_db_failing_commit() -> Iterator[CommitFailingSession]:
        session = Session(bind=_TEST_ENGINE)
        try:
            yield CommitFailingSession(session, allowed_commits=1)
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db_failing_commit

    response = client.post("/jobs", json={"handler": "echo", "payload": {}})
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Job created but could not be queued"

    job = _only_job()
    assert job.status == "pending"
    assert str(job.id) in caplog.text


def test_get_job_returns_job_fields(client: TestClient, queue: FakeQueue) -> None:
    """GET /jobs/{job_id} returns the created job."""
    create_resp = client.post(
        "/jobs", json={"handler": "echo", "payload": {"to": "a@example.com"}}
    )
    job_id = create_resp.json()["id"]

    get_resp = client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == job_id
    assert body["handler"] == "echo"
    assert body["payload"] == {"to": "a@example.com"}
    assert body["status"] == "pending"
    assert body["result"] is None
    assert body["error"] is None


def test_get_job_returns_404_for_unknown_id(
    client: TestClient, queue: FakeQueue
) -> None:
    """GET /jobs/{job_id} returns 404 when the job does not exist."""
    response = client.get(f"/jobs/{uuid4()}")
    assert response.status_code == 404, response.text


def test_create_then_get_round_trip(client: TestClient, queue: FakeQueue) -> None:
    """A job created via POST is retrievable via GET."""
    create_resp = client.post(
        "/jobs",
        json={"handler": "add_numbers", "payload": {"a": 1, "b": 2}},
    )
    job_id = create_resp.json()["id"]

    get_resp = client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["id"] == job_id
    assert body["handler"] == "add_numbers"
    assert body["status"] == "pending"
