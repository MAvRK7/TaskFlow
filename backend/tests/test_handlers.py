"""Tests for the handler registry and built-in handler contracts.

These cover behaviour added in Phase 3 that previously had no test: duplicate
name rejection, the registration bootstrap (design §5.1), and the demo handler
contracts (design §5, acceptance 4-6).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.jobs import registry
from app.jobs.handlers import add_numbers_handler, echo_handler
from app.jobs.registry import (
    load_builtin_handlers,
    register_handler,
    registered_handlers,
)

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_duplicate_handler_name_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registering the same handler name twice raises instead of overwriting."""

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        return payload

    # Isolate the registry so this test cannot leak entries into others.
    monkeypatch.setattr(registry, "_REGISTRY", {})

    register_handler("duplicate")(handler)
    with pytest.raises(ValueError, match="duplicate"):
        register_handler("duplicate")(handler)


def test_load_builtin_handlers_is_idempotent() -> None:
    """Loading the built-ins twice does not raise on duplicate registration."""
    load_builtin_handlers()
    load_builtin_handlers()

    assert {"add_numbers", "echo"} <= set(registered_handlers())


def test_importing_app_populates_registry() -> None:
    """Importing ``app.main`` alone is enough to register the demo handlers.

    Runs in a subprocess so the assertion reflects a fresh interpreter rather
    than a registry already populated by another test module's imports. Guards
    the API bootstrap site in design §5.1; the worker entry point gets the
    same guard once `app.workers` lands on `main`.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import app.main; "
                "from app.jobs.registry import registered_handlers; "
                "print(','.join(registered_handlers()))"
            ),
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert set(result.stdout.strip().split(",")) >= {"add_numbers", "echo"}


def test_echo_returns_payload_unchanged() -> None:
    """The echo handler returns its payload verbatim."""
    payload = {"to": "a@example.com", "nested": {"ids": [1, 2, 3]}}

    assert echo_handler(payload) == payload


def test_add_numbers_returns_sum() -> None:
    """The add_numbers handler sums numeric a and b."""
    assert add_numbers_handler({"a": 2, "b": 40}) == {"sum": 42}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="missing-both"),
        pytest.param({"a": 1}, id="missing-b"),
        pytest.param({"a": "1", "b": 2}, id="non-numeric-a"),
        pytest.param({"a": 1, "b": None}, id="null-b"),
        pytest.param({"a": True, "b": 2}, id="bool-a"),
        pytest.param({"a": 1, "b": False}, id="bool-b"),
    ],
)
def test_add_numbers_rejects_invalid_input(payload: dict[str, Any]) -> None:
    """add_numbers raises ValueError for missing, null, non-numeric or bool input."""
    handler: Callable[[dict[str, Any]], dict[str, Any] | None] = add_numbers_handler

    with pytest.raises(ValueError):
        handler(payload)
