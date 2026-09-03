"""Automation error classification."""

from __future__ import annotations

RETRYABLE_CODES = frozenset({
    "PROVIDER_TIMEOUT",
    "PROVIDER_429",
    "FILESYSTEM_LOCK",
    "ARCHIVE_FAILED",
    "TEMPORARY",
})

PERMANENT_CODES = frozenset({
    "UNKNOWN_FORMAT",
    "AMBIGUOUS_FORMAT",
    "TIMEZONE_REQUIRED",
    "MISSING_REQUIRED_COLUMN",
    "PARSER_ERROR",
    "UNSUPPORTED_TYPE",
    "INVALID_SOURCE",
})


def is_retryable(code: str | None) -> bool:
    return (code or "") in RETRYABLE_CODES
