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
from app.main import app

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


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
    """Provide a TestClient with the ``get_db`` dependency overridden.

    The override binds each request's session to the shared in-memory
    test engine. The override is cleared after the test so other test
    modules that import ``app`` are not affected.
    """

    def _override_get_db() -> Iterator[Session]:
        session = Session(bind=_TEST_ENGINE)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_create_job_returns_201_and_job_fields(client: TestClient) -> None:
    """POST /jobs creates a pending job and returns its fields."""
    response = client.post(
        "/jobs",
        json={"handler": "send_email", "payload": {"to": "a@example.com"}},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["handler"] == "send_email"
    assert body["payload"] == {"to": "a@example.com"}
    assert body["status"] == "pending"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


def test_create_job_defaults_payload_to_empty_object(client: TestClient) -> None:
    """POST /jobs without payload stores an empty object."""
    response = client.post("/jobs", json={"handler": "add_numbers"})
    assert response.status_code == 201, response.text
    assert response.json()["payload"] == {}


def test_create_job_missing_handler_returns_422(client: TestClient) -> None:
    """POST /jobs without a handler returns 422 for invalid input."""
    response = client.post("/jobs", json={"payload": {"to": "a@example.com"}})
    assert response.status_code == 422, response.text


def test_create_job_invalid_payload_type_returns_422(client: TestClient) -> None:
    """POST /jobs with a non-object payload returns 422."""
    response = client.post(
        "/jobs", json={"handler": "send_email", "payload": "not-a-dict"}
    )
    assert response.status_code == 422, response.text


def test_create_job_handler_too_long_returns_422(client: TestClient) -> None:
    """POST /jobs with a handler longer than the DB column (255) returns 422."""
    response = client.post("/jobs", json={"handler": "h" * 256})
    assert response.status_code == 422, response.text


def test_get_job_returns_job_fields(client: TestClient) -> None:
    """GET /jobs/{job_id} returns the created job."""
    create_resp = client.post(
        "/jobs", json={"handler": "send_email", "payload": {"to": "a@example.com"}}
    )
    job_id = create_resp.json()["id"]

    get_resp = client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == job_id
    assert body["handler"] == "send_email"
    assert body["payload"] == {"to": "a@example.com"}
    assert body["status"] == "pending"
    assert body["result"] is None
    assert body["error"] is None


def test_get_job_returns_404_for_unknown_id(client: TestClient) -> None:
    """GET /jobs/{job_id} returns 404 when the job does not exist."""
    response = client.get(f"/jobs/{uuid4()}")
    assert response.status_code == 404, response.text


def test_create_then_get_round_trip(client: TestClient) -> None:
    """A job created via POST is retrievable via GET."""
    create_resp = client.post(
        "/jobs",
        json={"handler": "process_image", "payload": {"path": "/tmp/img.png"}},
    )
    job_id = create_resp.json()["id"]

    get_resp = client.get(f"/jobs/{job_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["id"] == job_id
    assert body["handler"] == "process_image"
    assert body["status"] == "pending"
