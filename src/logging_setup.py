"""Daily-rotating log with credential redaction. Typed keys / passwords are never logged."""
from __future__ import annotations

import logging
import re
from logging.handlers import TimedRotatingFileHandler

from .paths import logs_dir

_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|session|cookie|set-cookie|authorization)\s*[:=]\s*[^\s,;&]+"), r"\1=***"),
    (re.compile(r"(?i)(bearer|basic)\s+[A-Za-z0-9._~+/=-]+"), r"\1 ***"),
    (re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@"), r"\1***@"),
]


def redact(text: str) -> str:
    for pat, rep in _PATTERNS:
        text = pat.sub(rep, text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        record.msg = redact(msg)
        record.args = ()
        if record.exc_info:  # redact tracebacks too
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        return True


_configured = False


def get_logger(name: str = "pttpost") -> logging.Logger:
    global _configured
    root = logging.getLogger("pttpost")
    if not _configured:
        root.setLevel(logging.INFO)
        try:
            h = TimedRotatingFileHandler(logs_dir() / "app.log", when="midnight", backupCount=30, encoding="utf-8", delay=True)
        except OSError:  # pragma: no cover
            h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"))
        h.addFilter(RedactFilter())
        root.addHandler(h)
        _configured = True
    return root if name == "pttpost" else logging.getLogger("pttpost." + name)
