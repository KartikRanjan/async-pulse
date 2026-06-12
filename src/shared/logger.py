"""Structured logging via structlog.

Initialise once at startup (``setup_logging`` called from ``core/lifespan.py``).
Module-level singleton — never constructor-injected (CODING_CONVENTIONS §16).
"""

import structlog


def setup_logging() -> None:
    """Configure structlog processors for structured JSON/console output."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
