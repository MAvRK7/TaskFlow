"""TaskFlow API routes.

Endpoints for job submission and retrieval. Database access is delegated
to the shared session dependency in ``app.db.session``; queue access is
delegated to the shared queue dependency in ``app.queue.client``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.jobs.models import Job, JobStatus
from app.jobs.registry import get_handler, registered_handlers
from app.jobs.schemas import JobCreate, JobRead
from app.queue.client import QueueProtocol, get_queue

logger = logging.getLogger(__name__)

#: Bound on the persisted error text, matching the worker's convention
#: (design doc §5) so no single row carries an unbounded traceback string.
MAX_ERROR_LENGTH = 2000

router = APIRouter()


def _record_enqueue_failure(db: Session, job: Job, exc: Exception) -> None:
    """Mark ``job`` as failed because it could not be queued.

    ``failed`` is terminal, so ``completed_at`` is set here too; anything that
    assumes terminal jobs have a completion timestamp then sees these rows.
    The cause is kept as ``"<ExceptionType>: <message>"`` truncated to
    :data:`MAX_ERROR_LENGTH`, while the client-facing detail stays generic.

    This function never raises. If the recovery write fails as well, the job
    stays ``pending`` (Phase 3 known limitation) and the job id is logged at
    ERROR so it can be reconciled later — the client still gets the documented
    503 rather than a 500.
    """
    # Read the id before committing: a failed commit/rollback expires the
    # instance, and re-loading attributes would fail with the same broken
    # connection that caused this path.
    job_id = job.id

    job.status = JobStatus.FAILED
    job.error = f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LENGTH]
    job.completed_at = datetime.now(UTC)
    try:
        db.commit()
    except Exception:
        # Recovery must not mask the 503 the client is owed.
        db.rollback()
        logger.exception(
            "Could not record enqueue failure for job %s; job left pending", job_id
        )


@router.post(
    "/jobs",
    status_code=status.HTTP_201_CREATED,
    response_model=JobRead,
    summary="Submit a new background job",
)
def create_job(
    job_create: JobCreate,
    db: Session = Depends(get_db),  # noqa: B008 - standard FastAPI dependency pattern
    queue: QueueProtocol = Depends(get_queue),  # noqa: B008 - standard FastAPI dependency pattern
) -> Job:
    """Create a new job with ``pending`` status and enqueue it for execution.

    The ``handler`` must name a registered job handler; otherwise the
    request is rejected with 422 listing the valid handlers. The job row
    is committed before enqueueing; if Redis is unavailable the job is
    marked ``failed`` with the cause recorded and the API returns 503 so
    nothing is silently stranded in ``pending``. If even the recovery write
    fails, the client still receives 503 and the job id is logged.
    """
    handler = get_handler(job_create.handler)
    if handler is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unknown handler '{job_create.handler}'. "
                f"Registered handlers: {', '.join(registered_handlers())}"
            ),
        )

    job = Job(handler=job_create.handler, payload=job_create.payload)
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        queue.enqueue(str(job.id))
    except Exception as exc:
        # Any enqueue failure (refused, timed out, auth) marks the job failed.
        _record_enqueue_failure(db, job, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job created but could not be queued",
        ) from exc

    return job


@router.get(
    "/jobs/{job_id}",
    response_model=JobRead,
    summary="Get job status and result",
)
def get_job(
    job_id: UUID,
    db: Session = Depends(get_db),  # noqa: B008 - standard FastAPI dependency pattern
) -> Job:
    """Return a job by ID, or 404 if it does not exist."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return job


__all__ = ["router"]
