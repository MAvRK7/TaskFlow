"""TaskFlow queue client.

Wraps Redis list operations for job enqueue/dequeue. The default
implementation uses Redis; tests inject an in-memory fake through
``get_queue()``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from redis import Redis

from app.core.config import get_settings

QUEUE_NAME = "taskflow:jobs"

#: Default ``BLPOP`` timeout for :meth:`QueueClient.dequeue`.
BLPOP_TIMEOUT_SECONDS = 5.0

#: TCP connect timeout. Bounds how long a blackholed Redis can stall
#: ``POST /jobs`` before the "mark failed + 503" path can run.
CONNECT_TIMEOUT_SECONDS = 2.0

#: Socket read timeout. Must stay above the blocking-pop timeout, otherwise
#: redis-py raises ``TimeoutError`` before ``BLPOP`` has a chance to return.
SOCKET_TIMEOUT_SECONDS = BLPOP_TIMEOUT_SECONDS + 2.0

#: How often idle connections are health-checked, so a dead pooled connection
#: is detected and replaced rather than failing the next real command.
HEALTH_CHECK_INTERVAL_SECONDS = 30.0


@runtime_checkable
class QueueProtocol(Protocol):
    """Protocol for queue clients used by API and worker code.

    Tests inject an in-memory fake implementing this protocol through
    ``get_queue()``; route code never sees Redis types.
    """

    def enqueue(self, job_id: str) -> None:
        """Push ``job_id`` onto the queue."""

    def dequeue(self, timeout: float = BLPOP_TIMEOUT_SECONDS) -> str | None:
        """Pop a job ID, blocking up to ``timeout`` seconds; ``None`` on timeout."""

    def close(self) -> None:
        """Release the underlying Redis connection pool."""


class QueueClient:
    """Redis-backed queue client.

    Uses a Redis list ``taskflow:jobs`` as a FIFO queue. Pushes job ID
    strings; pops them back with a blocking pop.
    """

    def __init__(self, redis_client: Redis | None = None) -> None:
        if redis_client is None:
            settings = get_settings()
            redis_client = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
                socket_timeout=SOCKET_TIMEOUT_SECONDS,
                health_check_interval=HEALTH_CHECK_INTERVAL_SECONDS,
            )
        self._client = redis_client

    def enqueue(self, job_id: str) -> None:
        """Push ``job_id`` onto the queue."""
        self._client.rpush(QUEUE_NAME, job_id)

    def dequeue(self, timeout: float = BLPOP_TIMEOUT_SECONDS) -> str | None:
        """Pop a job ID from the queue, blocking up to ``timeout`` seconds.

        Returns ``None`` when the timeout elapses with no item.
        """
        result = self._client.blpop(QUEUE_NAME, timeout=timeout)
        if result is None:
            return None
        _, value = result
        return value.decode() if isinstance(value, bytes) else value

    def close(self) -> None:
        """Close the underlying Redis connection pool."""
        self._client.close()


# Shared application-wide client. The Redis connection pool is reused
# across calls; only the QueueClient wrapper is yielded per request.
_client = QueueClient()


def get_queue() -> QueueProtocol:
    """Return the shared queue client for dependency injection.

    Intended for use as a FastAPI dependency:

        def route(queue: QueueProtocol = Depends(get_queue)): ...

    Tests override this dependency with an in-memory fake implementing
    QueueProtocol.
    """
    return _client


__all__ = [
    "BLPOP_TIMEOUT_SECONDS",
    "CONNECT_TIMEOUT_SECONDS",
    "HEALTH_CHECK_INTERVAL_SECONDS",
    "QUEUE_NAME",
    "SOCKET_TIMEOUT_SECONDS",
    "QueueClient",
    "QueueProtocol",
    "get_queue",
]
