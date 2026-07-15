"""Structured (JSON) logging — a generic helper with zero project-specific knowledge,
per docs/02_Folder_Guide.md's description of `utils/`. Introduced in v2.0 Step 7
because `RentCastConnector` is the first module needing to log real operational
events (retries, timeouts, pagination) in a form that stays greppable/parseable
regardless of which connector emitted it. Nothing before this sprint used `logging`
at all (see `docs/20_First_Production_Connector.md`), so there is no prior convention
to preserve — every field below is chosen for this first use, not inherited.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, logger name, message, and whatever
    extra key/value context the caller passed via `logger.info(msg, extra={...})`.
    """

    _RESERVED = set(logging.LogRecord(None, None, "", 0, "", None, None).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = {key: value for key, value in record.__dict__.items() if key not in self._RESERVED}
        payload.update(extra)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def get_logger(name: str) -> logging.Logger:
    """Returns a logger emitting one structured JSON line per record to stderr.
    Idempotent: calling this twice with the same `name` does not attach a second
    handler (a real risk since connectors may be instantiated more than once per
    process, e.g. once per platform per search).
    """
    logger = logging.getLogger(name)
    if not any(isinstance(handler, logging.StreamHandler) and isinstance(handler.formatter, StructuredFormatter) for handler in logger.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
