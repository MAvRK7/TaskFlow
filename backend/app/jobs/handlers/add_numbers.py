"""Add numbers handler — returns ``{"sum": a + b}``."""

from __future__ import annotations

from typing import Any

from app.jobs.registry import register_handler


@register_handler("add_numbers")
def add_numbers_handler(payload: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"sum": a + b}`` for numeric ``a`` and ``b`` keys.

    Raises ``ValueError`` when ``a`` or ``b`` is missing, non-numeric, or a
    boolean (bool is an int subclass in Python).
    """
    a = payload.get("a")
    b = payload.get("b")
    if a is None or b is None:
        raise ValueError("a and b are required")
    if isinstance(a, bool) or isinstance(b, bool):
        raise ValueError("a and b must be numbers, not booleans")  # noqa: TRY004
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise ValueError("a and b must be numbers")  # noqa: TRY004
    return {"sum": a + b}


__all__ = ["add_numbers_handler"]
