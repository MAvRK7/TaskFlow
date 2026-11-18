"""TaskFlow API routes.

Endpoints for job submission and retrieval. Database access is delegated
to the shared session dependency in ``app.db.session``; queue access is
delegated to the shared queue dependency in ``app.queue.client``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.jobs.models import Job, JobStatus
from app.jobs.registry import get_handler, registered_handlers
from app.jobs.schemas import JobCreate, JobRead
from app.queue.client import QueueProtocol, get_queue

router = APIRouter()


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
    marked ``failed`` and the API returns 503 so nothing is silently
    stranded in ``pending``.
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
    except Exception:  # noqa: BLE001 - any enqueue failure marks job failed
        job.status = JobStatus.FAILED
        job.error = "Queue unavailable: job could not be enqueued"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job created but could not be queued",
        )

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
