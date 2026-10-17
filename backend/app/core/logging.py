"""JSON logging: one line per event, with the request id attached to everything logged during a
request.

structlog's standard-library integration renders uvicorn's and SQLAlchemy's own log records in the
same JSON shape, so the hosting platform's log viewer shows a single consistent stream. Names,
phone numbers, dates of birth and reasons are never logged; only ids, codes and timings.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.typing import Processor


def configure_logging(level: str) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []  # propagate to the root handler instead
        logging.getLogger(name).propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
