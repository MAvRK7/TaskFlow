"""TaskFlow worker entry point.

Run with: ``python -m app.workers``

Loads the job handlers before the worker starts dequeuing, so their
``@register_handler`` decorators have populated the registry.
"""

from __future__ import annotations

import logging
import signal
from types import FrameType

from app.jobs.registry import load_builtin_handlers
from app.queue.client import QueueClient
from app.workers.worker import request_stop, run_worker

load_builtin_handlers()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _handle_signal(signum: int, frame: FrameType | None) -> None:
    """Request a graceful stop; the current job finishes first."""
    request_stop()
    logger.info("Received signal %s, will finish current job and exit", signum)


def main() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    queue = QueueClient()
    try:
        run_worker(queue)
    finally:
        queue.close()


if __name__ == "__main__":
    main()
