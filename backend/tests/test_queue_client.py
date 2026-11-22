"""Tests for the TaskFlow queue client.

Uses a stub Redis object (no real Redis required) so the default test run
needs no external services.
"""

from __future__ import annotations

from app.queue.client import (
    BLPOP_TIMEOUT_SECONDS,
    CONNECT_TIMEOUT_SECONDS,
    SOCKET_TIMEOUT_SECONDS,
    QueueClient,
    QueueProtocol,
    get_queue,
)


class StubRedis:
    """In-memory stub of redis.Redis for testing QueueClient."""

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {}
        self.blpop_calls: list[tuple[str, float]] = []

    def rpush(self, key: str, *values: str) -> int:
        self._store.setdefault(key, []).extend(values)
        return len(self._store[key])

    def blpop(self, key: str, timeout: float) -> tuple[str, str] | None:
        self.blpop_calls.append((key, timeout))
        store = self._store.get(key, [])
        if store:
            value = store.pop(0)
            return (key, value)
        return None


def test_enqueue_pushes_to_taskflow_jobs() -> None:
    """enqueue calls rpush on taskflow:jobs with the job id."""
    stub = StubRedis()
    client = QueueClient(redis_client=stub)  # type: ignore[arg-type]

    client.enqueue("job-123")

    assert stub._store["taskflow:jobs"] == ["job-123"]


def test_dequeue_returns_none_when_empty() -> None:
    """dequeue returns None when the queue is empty."""
    stub = StubRedis()
    client = QueueClient(redis_client=stub)  # type: ignore[arg-type]

    result = client.dequeue(timeout=5.0)

    assert result is None


def test_dequeue_decodes_bytes() -> None:
    """dequeue decodes a bytes value returned by blpop."""
    stub = StubRedis()
    stub._store["taskflow:jobs"] = ["job-456"]
    client = QueueClient(redis_client=stub)  # type: ignore[arg-type]

    result = client.dequeue(timeout=5.0)

    assert result == "job-456"


def test_dequeue_forwards_timeout_unchanged() -> None:
    """dequeue passes the timeout to blpop without truncation."""
    stub = StubRedis()
    client = QueueClient(redis_client=stub)  # type: ignore[arg-type]

    client.dequeue(timeout=2.5)

    assert stub.blpop_calls == [("taskflow:jobs", 2.5)]


def test_get_queue_returns_queue_protocol() -> None:
    """get_queue returns an object implementing QueueProtocol."""
    queue = get_queue()
    assert isinstance(queue, QueueProtocol)


def test_queue_client_bounds_redis_timeouts() -> None:
    """The Redis client sets connect/read timeouts so failures surface fast.

    Without these, a blackholed Redis (dropped packets rather than a refused
    connection) makes ``POST /jobs`` hang for the OS TCP timeout instead of
    taking the documented 503 path.
    """
    client = QueueClient()

    kwargs = client._client.connection_pool.connection_kwargs  # type: ignore[attr-defined]
    assert kwargs["socket_connect_timeout"] == CONNECT_TIMEOUT_SECONDS
    assert kwargs["socket_timeout"] == SOCKET_TIMEOUT_SECONDS
    assert kwargs["health_check_interval"] > 0


def test_socket_timeout_exceeds_blocking_pop_timeout() -> None:
    """BLPOP must be able to return before the socket read times out."""
    assert SOCKET_TIMEOUT_SECONDS > BLPOP_TIMEOUT_SECONDS


def test_dequeue_defaults_to_blocking_pop_timeout() -> None:
    """dequeue() blocks for the documented default timeout."""
    stub = StubRedis()
    client = QueueClient(redis_client=stub)  # type: ignore[arg-type]

    client.dequeue()

    assert stub.blpop_calls == [("taskflow:jobs", BLPOP_TIMEOUT_SECONDS)]
