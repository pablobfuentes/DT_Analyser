"""Structured Pine import errors."""

from __future__ import annotations


class PineParseError(Exception):
    def __init__(self, code: str, message: str, raw_line: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.raw_line = raw_line
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "raw_line": self.raw_line,
            "details": self.details,
        }
