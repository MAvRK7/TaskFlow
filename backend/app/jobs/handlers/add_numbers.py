"""Add numbers handler — returns ``{"sum": a + b}``."""

from __future__ import annotations

from typing import Any

from app.jobs.registry import register_handler


@register_handler("add_numbers")
def add_numbers_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"sum": a + b}`` for numeric ``a`` and ``b`` keys."""
    a = payload.get("a", 0)
    b = payload.get("b", 0)
    return {"sum": a + b}


__all__ = ["add_numbers_handler"]
