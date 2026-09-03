"""Centralized market-data quality statuses."""

from enum import StrEnum


class QualityStatus(StrEnum):
    OK = "OK"
    PARTIAL_FEED = "PARTIAL_FEED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MISSING_BAR = "MISSING_BAR"
    CORPORATE_ACTION_AMBIGUITY = "CORPORATE_ACTION_AMBIGUITY"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PENDING_EOD = "PENDING_EOD"


class EnrichmentStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    PENDING_EOD = "PENDING_EOD"
