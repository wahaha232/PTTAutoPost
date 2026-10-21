"""Layered exceptions (same convention as the user's other Python tools)."""
from __future__ import annotations


class ToolError(Exception):
    """Base class: the UI only needs to catch this."""

    code = "E-TOOL"

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.message = message
        self.detail = detail

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.message}" + (f" ({self.detail})" if self.detail else "")


class InputError(ToolError):
    code = "E-INPUT"


class FetchError(ToolError):
    code = "E-FETCH"


class ParseError(ToolError):
    code = "E-PARSE"


class ValidationError(ToolError):
    code = "E-CHECK"


class StorageError(ToolError):
    code = "E-DB"


class ConnectionFailed(ToolError):
    code = "E-CONN"


class DeliveryError(ToolError):
    code = "E-DELIVERY"
