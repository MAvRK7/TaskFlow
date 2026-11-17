"""Pydantic schemas for job request and response bodies.

These schemas define the API contract. Responses are serialized through
these schemas rather than returning raw SQLAlchemy model instances, so
internal database implementation details are not exposed to API clients.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    """Request body for creating a new job."""

    # Length bounds mirror the ``Job.handler`` column (``String(255)``) so
    # oversized names are rejected with 422 at the API boundary instead of
    # surfacing as a database error on commit (PostgreSQL enforces the
    # column length; SQLite does not).
    handler: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    """Response body for a job.

    Exposes only the API-facing fields. Internal SQLAlchemy implementation
    details are not exposed.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    handler: str
    payload: dict[str, Any]
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
