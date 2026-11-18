"""Tests for the TaskFlow job API routes.

Tests run against an in-memory SQLite database by overriding the
``get_db`` dependency, so no live PostgreSQL instance is required.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.jobs.models import Job
from app.main import app
from app.queue.client import QueueProtocol, get_queue

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
def client() -> Iterator[TestClient]:
    """Provide a TestClient with ``get_db`` and ``get_queue`` overridden.

    The overrides bind each request's session to the shared in-memory
    test engine and record enqueued job IDs on a fake queue. Overrides
    are cleared after the test so other test modules that import ``app``
    are not affected.
    """

    def _override_get_db() -> Iterator[Session]:
        session = Session(bind=_TEST_ENGINE)
        try:
            yield session
        finally:
            session.close()

    fake_queue = FakeQueue()

    def _override_get_queue() -> QueueProtocol:
        return fake_queue  # type: ignore[return-value]

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_queue] = _override_get_queue
    yield TestClient(app), fake_queue
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_queue, None)


def test_create_job_returns_201_and_job_fields(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """POST /jobs creates a pending job and returns its fields."""
    test_client, fake_queue = client
    response = test_client.post(
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
    assert fake_queue.enqueued == [body["id"]]


def test_create_job_defaults_payload_to_empty_object(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """POST /jobs without payload stores an empty object."""
    test_client, _ = client
    response = test_client.post("/jobs", json={"handler": "add_numbers"})
    assert response.status_code == 201, response.text
    assert response.json()["payload"] == {}


def test_create_job_missing_handler_returns_422(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """POST /jobs without a handler returns 422 for invalid input."""
    test_client, _ = client
    response = test_client.post("/jobs", json={"payload": {"to": "a@example.com"}})
    assert response.status_code == 422, response.text


def test_create_job_invalid_payload_type_returns_422(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """POST /jobs with a non-object payload returns 422."""
    test_client, _ = client
    response = test_client.post(
        "/jobs", json={"handler": "echo", "payload": "not-a-dict"}
    )
    assert response.status_code == 422, response.text


def test_create_job_handler_too_long_returns_422(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """POST /jobs with a handler longer than the DB column (255) returns 422."""
    test_client, _ = client
    response = test_client.post("/jobs", json={"handler": "h" * 256})
    assert response.status_code == 422, response.text


def test_create_job_unregistered_handler_returns_422(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """POST /jobs with an unregistered handler returns 422, no row, no queue entry."""
    test_client, fake_queue = client
    response = test_client.post(
        "/jobs", json={"handler": "nonexistent_handler", "payload": {}}
    )
    assert response.status_code == 422, response.text
    body = response.json()
    assert "nonexistent_handler" in body["detail"]
    assert "echo" in body["detail"]
    assert "add_numbers" in body["detail"]
    assert fake_queue.enqueued == []
    # No row should exist in the database
    session = Session(bind=_TEST_ENGINE)
    count = session.query(Job).count()
    session.close()
    assert count == 0


def test_create_job_enqueue_failure_returns_503(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """POST /jobs when enqueue raises returns 503 and marks job failed."""
    test_client, fake_queue = client

    def failing_enqueue(job_id: str) -> None:
        raise RuntimeError("Redis is down")

    fake_queue.enqueue = failing_enqueue  # type: ignore[method-assign]

    response = test_client.post("/jobs", json={"handler": "echo", "payload": {}})
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["detail"] == "Job created but could not be queued"

    # The job row should exist with status=failed and error set
    session = Session(bind=_TEST_ENGINE)
    job = session.query(Job).filter(Job.handler == "echo").first()
    session.close()
    assert job is not None
    assert job.status == "failed"
    assert job.error is not None
    assert "could not be enqueued" in job.error


def test_get_job_returns_job_fields(client: tuple[TestClient, FakeQueue]) -> None:
    """GET /jobs/{job_id} returns the created job."""
    test_client, _ = client
    create_resp = test_client.post(
        "/jobs", json={"handler": "echo", "payload": {"to": "a@example.com"}}
    )
    job_id = create_resp.json()["id"]

    get_resp = test_client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == job_id
    assert body["handler"] == "echo"
    assert body["payload"] == {"to": "a@example.com"}
    assert body["status"] == "pending"
    assert body["result"] is None
    assert body["error"] is None


def test_get_job_returns_404_for_unknown_id(
    client: tuple[TestClient, FakeQueue],
) -> None:
    """GET /jobs/{job_id} returns 404 when the job does not exist."""
    test_client, _ = client
    response = test_client.get(f"/jobs/{uuid4()}")
    assert response.status_code == 404, response.text


def test_create_then_get_round_trip(client: tuple[TestClient, FakeQueue]) -> None:
    """A job created via POST is retrievable via GET."""
    test_client, _ = client
    create_resp = test_client.post(
        "/jobs",
        json={"handler": "add_numbers", "payload": {"a": 1, "b": 2}},
    )
    job_id = create_resp.json()["id"]

    get_resp = test_client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["id"] == job_id
    assert body["handler"] == "add_numbers"
    assert body["status"] == "pending"
