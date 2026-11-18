"""TaskFlow queue client.

Wraps Redis list operations for job enqueue/dequeue. The default
implementation uses Redis; tests inject an in-memory fake through
``get_queue()``.
"""

from __future__ import annotations

from collections.abc import Iterator

from redis import Redis

from app.core.config import get_settings

QUEUE_NAME = "taskflow:jobs"


class QueueClient:
    """Redis-backed queue client.

    Uses a Redis list ``taskflow:jobs`` as a FIFO queue. Pushes job ID
    strings; pops them back with a blocking pop.
    """

    def __init__(self, redis_client: Redis | None = None) -> None:
        if redis_client is None:
            settings = get_settings()
            redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        self._client = redis_client

    def enqueue(self, job_id: str) -> None:
        """Push ``job_id`` onto the queue."""
        self._client.rpush(QUEUE_NAME, job_id)

    def dequeue(self, timeout: float = 5.0) -> str | None:
        """Pop a job ID from the queue, blocking up to ``timeout`` seconds.

        Returns ``None`` when the timeout elapses with no item.
        """
        result = self._client.blpop(QUEUE_NAME, timeout=int(timeout))
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


def get_queue() -> Iterator[QueueClient]:
    """Yield a queue client for dependency injection.

    Intended for use as a FastAPI dependency:

        def route(queue: QueueClient = Depends(get_queue)): ...

    Tests override this dependency with an in-memory fake.
    """
    try:
        yield _client
    finally:
        pass


__all__ = ["QUEUE_NAME", "QueueClient", "get_queue"]
