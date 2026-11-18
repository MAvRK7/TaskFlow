"""Job handler registry.

Maps handler names to handler callables. Handlers self-register via the
``register_handler`` decorator when their module is imported. The API layer
uses ``get_handler`` to validate submissions; the worker layer uses it to
dispatch execution. Both import from here, so no circular dependency.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

HandlerFunc = Callable[[dict[str, Any]], dict[str, Any] | None]

_REGISTRY: dict[str, HandlerFunc] = {}


def register_handler(name: str) -> Callable[[HandlerFunc], HandlerFunc]:
    """Register a job handler under ``name``.

    Used as a decorator on handler functions in :mod:`app.jobs.handlers`.
    Importing those modules (e.g. from ``app.main`` or ``app.workers``)
    populates this registry so that POST /jobs can validate handler names
    and workers can dispatch them.
    """

    def decorator(func: HandlerFunc) -> HandlerFunc:
        _REGISTRY[name] = func
        return func

    return decorator


def get_handler(name: str) -> HandlerFunc | None:
    """Return the registered handler for ``name``, or ``None`` if unknown."""
    return _REGISTRY.get(name)


def registered_handlers() -> list[str]:
    """Return a sorted list of registered handler names."""
    return sorted(_REGISTRY.keys())


__all__ = ["HandlerFunc", "get_handler", "register_handler", "registered_handlers"]
