"""TaskFlow API routes.

Endpoints for job submission and retrieval. Database access is delegated
to the shared session dependency in ``app.db.session``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.jobs.models import Job
from app.jobs.schemas import JobCreate, JobRead

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
) -> Job:
    """Create a new job with ``pending`` status.

    The ``handler`` identifies a registered job handler. Workers look up
    handlers by name from a registry; arbitrary user-supplied code is
    never executed.

    Handler-registry validation is intentionally deferred to Phase 3
    (workers), when the registry itself exists: until then any
    well-formed handler name is accepted, so a typo'd name produces a
    job that stays ``pending`` rather than an immediate rejection.
    """
    job = Job(handler=job_create.handler, payload=job_create.payload)
    db.add(job)
    db.commit()
    db.refresh(job)

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
