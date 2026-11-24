"""Tests for the synchronous worker.

Runs against an in-memory SQLite database: the worker's session factory is
monkeypatched, so no PostgreSQL or Redis is required.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.jobs import registry
from app.jobs.models import Job, JobStatus
from app.jobs.registry import load_builtin_handlers
from app.workers import worker

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_SESSION_LOCAL = sessionmaker(
    bind=_TEST_ENGINE, autoflush=False, autocommit=False, class_=Session
)

load_builtin_handlers()


class ScriptedQueue:
    """Queue fake that replays a script of dequeue results.

    Each item is either a job id (returned once) or an exception instance
    (raised once). When the script is exhausted it calls
    :func:`worker.request_stop` so the loop terminates.
    """

    def __init__(
        self, *script: str | Exception, stop_when_exhausted: bool = True
    ) -> None:
        self._script = list(script)
        self._lock = Lock()
        self.dequeue_calls = 0
        self._stop_when_exhausted = stop_when_exhausted

    def enqueue(self, job_id: str) -> None:  # pragma: no cover - not used
        raise NotImplementedError

    def dequeue(self, timeout: float = 0.0) -> str | None:
        with self._lock:
            self.dequeue_calls += 1
            if self._script:
                item = self._script.pop(0)
            else:
                item = None
                if self._stop_when_exhausted:
                    worker.request_stop()
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:  # pragma: no cover - nothing to close
        pass


@pytest.fixture(autouse=True)
def setup_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give the worker an in-memory session factory and a clean schema."""
    Base.metadata.create_all(_TEST_ENGINE)
    monkeypatch.setattr(worker, "get_session_local", lambda: _SESSION_LOCAL)
    yield
    Base.metadata.drop_all(_TEST_ENGINE)


def _create_job(handler: str = "echo", payload: dict[str, Any] | None = None) -> UUID:
    """Insert a pending job and return its id."""
    with _SESSION_LOCAL() as session:
        job = Job(handler=handler, payload=payload or {})
        session.add(job)
        session.commit()
        return job.id


def _get_job(job_id: UUID) -> Job:
    """Return a detached copy of the job row."""
    with _SESSION_LOCAL() as session:
        job = session.scalars(select(Job).where(Job.id == job_id)).one()
        session.expunge(job)
        return job


def _register_temp_handler(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    func: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> None:
    """Register a handler for one test without polluting the global registry."""
    monkeypatch.setitem(registry._REGISTRY, name, func)


def test_claim_job_is_idempotent() -> None:
    """A pending job is claimed once; the second claim reports it lost the race."""
    job_id = _create_job()

    with _SESSION_LOCAL() as session:
        assert worker.claim_job(session, job_id) is True

    with _SESSION_LOCAL() as session:
        assert worker.claim_job(session, job_id) is False

    job = _get_job(job_id)
    assert job.status == JobStatus.RUNNING
    assert job.started_at is not None


def test_process_job_completes_and_records_result() -> None:
    """A successful run stores the handler result and both timestamps."""
    payload = {"to": "a@example.com"}
    job_id = _create_job("echo", payload)

    with _SESSION_LOCAL() as session:
        worker.process_job(str(job_id), session)

    job = _get_job(job_id)
    assert job.status == JobStatus.COMPLETED
    assert job.result == payload
    assert job.error is None
    assert job.started_at is not None
    assert job.completed_at is not None


def test_process_job_marks_unknown_handler_failed() -> None:
    """A job naming an unregistered handler fails instead of staying pending."""
    job_id = _create_job("handler_that_does_not_exist")

    with _SESSION_LOCAL() as session:
        worker.process_job(str(job_id), session)

    job = _get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert job.error is not None and "handler_that_does_not_exist" in job.error
    assert job.result is None
    assert job.completed_at is not None


def test_process_job_marks_handler_error_failed() -> None:
    """A handler that raises fails the job with the exception type and message."""
    job_id = _create_job("add_numbers", {})

    with _SESSION_LOCAL() as session:
        worker.process_job(str(job_id), session)

    job = _get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert job.error is not None and job.error.startswith("ValueError: ")
    assert job.completed_at is not None


def test_process_job_marks_non_dict_result_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handler returning a non-dict fails the job with a contract error."""
    _register_temp_handler(monkeypatch, "returns_str", lambda payload: "nope")
    job_id = _create_job("returns_str")

    with _SESSION_LOCAL() as session:
        worker.process_job(str(job_id), session)

    job = _get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert job.error is not None and "non-dict" in job.error
    assert job.completed_at is not None


def test_process_job_marks_non_serialisable_result_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A handler returning a non-JSON-serialisable dict fails before commit."""
    _register_temp_handler(monkeypatch, "returns_set", lambda payload: {"ids": {1, 2}})
    job_id = _create_job("returns_set")

    with _SESSION_LOCAL() as session:
        worker.process_job(str(job_id), session)

    job = _get_job(job_id)
    assert job.status == JobStatus.FAILED
    assert job.error is not None and "JSON-serialisable" in job.error
    assert job.result is None
    assert job.completed_at is not None


def test_process_job_discards_malformed_queue_entry() -> None:
    """A non-UUID queue entry is logged and discarded without touching any job."""
    pending_id = _create_job()

    with _SESSION_LOCAL() as session:
        worker.process_job("not-a-uuid", session)

    job = _get_job(pending_id)
    assert job.status == JobStatus.PENDING


def test_process_job_does_not_reprocess_completed_job() -> None:
    """A duplicate queue entry cannot re-execute a terminal job."""
    job_id = _create_job("echo", {"n": 1})

    with _SESSION_LOCAL() as session:
        worker.process_job(str(job_id), session)

    first = _get_job(job_id)

    with _SESSION_LOCAL() as session:
        worker.process_job(str(job_id), session)

    second = _get_job(job_id)
    assert second.status == JobStatus.COMPLETED
    assert second.completed_at == first.completed_at
    assert second.result == first.result


def test_run_worker_processes_job_then_stops() -> None:
    """The loop processes a dequeued job and exits once a stop is requested."""
    job_id = _create_job("echo", {"n": 1})
    queue = ScriptedQueue(str(job_id))

    worker.run_worker(queue)  # type: ignore[arg-type]

    job = _get_job(job_id)
    assert job.status == JobStatus.COMPLETED
    assert queue.dequeue_calls == 2


def test_run_worker_backs_off_when_dequeue_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing Redis connection pauses instead of spinning the event loop."""
    sleeps: list[float] = []
    monkeypatch.setattr(worker.time, "sleep", sleeps.append)
    queue = ScriptedQueue(RuntimeError("Redis is down"))

    worker.run_worker(queue)  # type: ignore[arg-type]

    assert sleeps == [worker.DEQUEUE_ERROR_BACKOFF_SECONDS]


def test_unknown_job_id_is_ignored() -> None:
    """A well-formed job id that no longer exists in the database is discarded."""
    missing = uuid4()
    queue = ScriptedQueue(str(missing))

    worker.run_worker(queue)  # type: ignore[arg-type]

    assert _count_jobs() == 0


def _count_jobs() -> int:
    with _SESSION_LOCAL() as session:
        return len(session.scalars(select(Job)).all())
