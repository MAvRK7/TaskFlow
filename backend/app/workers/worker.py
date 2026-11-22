"""TaskFlow synchronous worker.

Dequeues job IDs from Redis, claims jobs in PostgreSQL with a conditional
UPDATE, executes registered handlers, and updates job status/result/error.

Responsibilities (kept separate from API, database, and queue layers):
- Dequeue job IDs from Redis list ``taskflow:jobs`` with BLPOP timeout 5.
- Atomically claim pending jobs via ``UPDATE ... WHERE status = 'pending'``.
- Execute only registered handlers; never run arbitrary user-supplied code.
- Validate handler return values before marking a job completed.
- One SQLAlchemy Session per job; closed when the job is done.
- Handle SIGINT/SIGTERM by finishing the current job then exiting.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.db.session import get_session_local
from app.jobs.models import Job, JobStatus
from app.jobs.registry import get_handler
from app.queue.client import QueueProtocol, get_queue

logger = logging.getLogger(__name__)

MAX_ERROR_LENGTH = 2000
DEQUEUE_TIMEOUT = 5.0

# Set by signal handlers in __main__.py. When True, the worker finishes
# the current job and exits.
_stop = False


def request_stop() -> None:
    """Request the worker to stop after the current job completes."""
    global _stop
    _stop = True


def _format_error(exc: Exception) -> str:
    """Format an exception for storage in the Job.error column.

    Format: ``ExcType: message`` truncated to MAX_ERROR_LENGTH chars.
    The full traceback goes to the worker log, not the database.
    """
    return f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]


def claim_job(db: Session, job_id: uuid.UUID) -> bool:
    """Atomically claim a pending job by setting status to running.

    Uses a single conditional UPDATE so that two workers never claim the
    same job. Returns True if the job was claimed, False if it was already
    claimed by another worker or is in a terminal state.
    """
    result = db.execute(
        update(Job)
        .where(Job.id == job_id)
        .where(Job.status == JobStatus.PENDING)
        .values(status=JobStatus.RUNNING, started_at=func.now())
    )
    db.commit()
    return result.rowcount > 0  # type: ignore[attr-defined]


def process_job(job_id_str: str, db: Session) -> None:
    """Process a single job: claim, execute handler, set terminal state.

    If the job is already claimed or terminal, returns without changes.
    If the handler is unknown, marks the job failed. If the handler raises
    or returns an invalid result, marks the job failed with the error.
    """
    # Validate job_id is a UUID
    try:
        job_id = uuid.UUID(job_id_str)
    except ValueError:
        logger.warning("Malformed queue entry: %r", job_id_str)
        return

    # Claim the job: single conditional UPDATE
    if not claim_job(db, job_id):
        # Already claimed by another worker or already terminal
        return

    # Fetch the job (should now be RUNNING)
    job = db.get(Job, job_id)
    if job is None:
        logger.warning("Job %s not found after claim", job_id)
        return

    # Get handler from registry
    handler = get_handler(job.handler)
    if handler is None:
        job.status = JobStatus.FAILED
        job.error = f"Unknown handler: {job.handler}"[:MAX_ERROR_LENGTH]
        db.commit()
        return

    # Execute handler
    try:
        result = handler(job.payload)
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = _format_error(exc)
        logger.exception("Job %s handler %s failed", job.id, job.handler)
        db.commit()
        return

    # Validate result is dict or None
    if result is not None:
        if not isinstance(result, dict):
            job.status = JobStatus.FAILED
            job.error = (f"Handler returned non-dict: {type(result).__name__}")[
                :MAX_ERROR_LENGTH
            ]
            db.commit()
            return
        try:
            json.dumps(result)
        except (TypeError, ValueError) as exc:
            job.status = JobStatus.FAILED
            job.error = f"Handler result not JSON-serialisable: {exc}"[
                :MAX_ERROR_LENGTH
            ]
            db.commit()
            return

    # Success
    job.status = JobStatus.COMPLETED
    job.result = result
    job.completed_at = datetime.now(UTC)
    db.commit()


def run_worker(queue: QueueProtocol | None = None) -> None:
    """Main worker loop: dequeue, claim, execute, set terminal state.

    Runs until :func:`request_stop` is called (via SIGINT/SIGTERM).
    Finishes the current job before exiting.
    """
    if queue is None:
        queue = get_queue()

    global _stop
    _stop = False

    logger.info("Worker started")

    while not _stop:
        try:
            job_id_str = queue.dequeue(timeout=DEQUEUE_TIMEOUT)
        except Exception:
            logger.exception("Queue dequeue failed, retrying")
            continue

        if job_id_str is None:
            # Timeout — no job available, loop again to check _stop
            continue

        db = get_session_local()()
        try:
            process_job(job_id_str, db)
        except Exception:
            logger.exception("Unexpected error processing job %s", job_id_str)
            try:
                db.rollback()
            except Exception:
                logger.exception("Failed to rollback session")
        finally:
            db.close()

    logger.info("Worker stopped")


__all__ = ["request_stop", "run_worker"]
