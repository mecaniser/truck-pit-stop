"""
Structured Logging Configuration

Provides JSON-formatted logs for production and pretty-printed logs for development.
All logs include correlation IDs for request tracing.
"""
import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from app.core.config import settings
from app.core.redaction import (
    install_sensitive_data_filters,
    redact_structlog_event,
)


def get_log_level() -> int:
    """Get log level from settings."""
    levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return levels.get(settings.LOG_LEVEL.upper(), logging.INFO)


def setup_logging() -> None:
    """
    Configure structlog for the application.
    
    - Development: Pretty-printed, colored output
    - Production: JSON format for log aggregation
    """
    # Shared processors for all environments
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        redact_structlog_event,
    ]
    
    if settings.LOG_FORMAT == "json":
        # Production: JSON output
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
        
        # Configure standard logging to use structlog
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=get_log_level(),
        )
    else:
        # Development: Pretty console output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
        
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=get_log_level(),
        )
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Suppress noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    install_sensitive_data_filters()


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Usage:
        from app.core.logging import get_logger
        logger = get_logger(__name__)
        logger.info("user_login", user_id=123, ip="1.2.3.4")
    """
    return structlog.get_logger(name)


# Convenience function for binding context
def bind_contextvars(**kwargs: Any) -> None:
    """
    Bind variables to the logging context for the current request.
    
    Usage:
        bind_contextvars(user_id=123, tenant_id=456)
        # All subsequent logs will include user_id and tenant_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_contextvars() -> None:
    """Clear all context variables (call at end of request)."""
    structlog.contextvars.clear_contextvars()


def unbind_contextvars(*keys: str) -> None:
    """Remove specific keys from context."""
    structlog.contextvars.unbind_contextvars(*keys)
