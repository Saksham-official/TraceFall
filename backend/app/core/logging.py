"""Structured JSON logging with a per-request correlation id.

Secrets are redacted at the formatter, so a careless log.info(config) cannot leak one.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# The closing quote of a JSON key has to be allowed before the separator. Without it
# `{"secret_key": "s3cr3t"}` passed straight through — and JSON is this application's log
# format, so a logged settings dict was exactly the leak the redactor exists to prevent.
_SECRET_KEY_PATTERN = re.compile(
    r"(?i)\b([\w.]*(?:secret|password|token|api_key|apikey)[\w.]*)\b['\"]?\s*[=:]\s*['\"]?([^\s,'\"}]+)"
)


def redact(message: str) -> str:
    return _SECRET_KEY_PATTERN.sub(r"\1=***", message)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "request_id": request_id_var.get(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
