"""TaskFlow worker entry point.

Run with: ``python -m app.workers``

Imports job handlers at module scope so their ``@register_handler``
decorators populate the registry before the worker starts dequeuing.
"""

from __future__ import annotations

import logging
import signal

from app.queue.client import QueueClient
from app.workers.worker import request_stop, run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def _handle_signal(signum, frame):
    _stop_ref()
    logger.info("Received signal %s, will finish current job and exit", signum)


_stop_ref = request_stop


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
