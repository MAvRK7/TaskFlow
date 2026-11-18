"""TaskFlow job handlers.

Modules in this package self-register via
:func:`app.jobs.registry.register_handler`. Importing this package populates
the registry so that the API can validate submissions and workers can
dispatch execution.
"""

from .add_numbers import add_numbers_handler
from .echo import echo_handler

__all__ = ["add_numbers_handler", "echo_handler"]
