"""Echo handler — returns its input payload."""

from __future__ import annotations

from typing import Any

from app.jobs.registry import register_handler


@register_handler("echo")
def echo_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the payload unchanged."""
    return payload


__all__ = ["echo_handler"]
