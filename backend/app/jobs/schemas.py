"""Pydantic schemas for job request and response bodies.

These schemas define the API contract. Responses are serialized through
these schemas rather than returning raw SQLAlchemy model instances, so
internal database implementation details are not exposed to API clients.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Maximum serialised JSON size of a job payload, in bytes.
#:
#: Bounds the memory and storage cost of a single submission: the payload is
#: copied into ``Job.payload`` and, for handlers like ``echo``, into
#: ``Job.result``, so an unbounded body is a cheap way to exhaust the API.
MAX_PAYLOAD_BYTES = 64 * 1024


class JobCreate(BaseModel):
    """Request body for creating a new job."""

    # Length bounds mirror the ``Job.handler`` column (``String(255)``) so
    # oversized names are rejected with 422 at the API boundary instead of
    # surfacing as a database error on commit (PostgreSQL enforces the
    # column length; SQLite does not).
    handler: str = Field(min_length=1, max_length=255)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def _payload_within_size_limit(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """Reject payloads whose compact JSON encoding exceeds the cap."""
        size = len(json.dumps(payload, separators=(",", ":")).encode())
        if size > MAX_PAYLOAD_BYTES:
            raise ValueError(
                f"payload must be at most {MAX_PAYLOAD_BYTES} bytes of JSON, got {size}"
            )
        return payload


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
