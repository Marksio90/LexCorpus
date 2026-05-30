"""
logging_config.py — Structured JSON logging for the LexCorpus API.

In production (LOG_FORMAT=json), each log line is a JSON object with
timestamp, level, logger name, message, and any extra fields.
In development (default), uses the standard human-readable format.

PII note: question text is logged at INFO level (for debugging). If PII
masking is required, set LOG_MASK_QUESTIONS=true to replace query content
with a placeholder.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_MASK_QUESTIONS = os.getenv("LOG_MASK_QUESTIONS", "false").lower() not in ("false", "0", "no")


class _QuestionMaskFilter(logging.Filter):
    """Redact question text from log records when LOG_MASK_QUESTIONS=true."""

    _MARKERS = ("Question:", "question=", "query=")

    def filter(self, record: logging.LogRecord) -> bool:
        if _MASK_QUESTIONS:
            msg = record.getMessage()
            for marker in self._MARKERS:
                if marker in msg:
                    record.msg = f"{marker} [REDACTED]"
                    record.args = ()
                    break
        return True


def configure_logging() -> None:
    log_format = os.getenv("LOG_FORMAT", "text").lower()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler(sys.stdout)

    if log_format == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    if _MASK_QUESTIONS:
        handler.addFilter(_QuestionMaskFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))

    # Suppress noisy third-party loggers
    for noisy in ("uvicorn.access", "httpx", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
