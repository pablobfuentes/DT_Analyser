"""Content-based inbox classification. Reuses Step 1 detector and Step 5 Pine parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.importers.detector import preview_file
from app.importers.exceptions import TimezoneRequiredError
from app.services.signals.parser import parse_pine_log
from app.utils.hashing import sha256_file

IGNORE_SUFFIXES = (".tmp", ".part", ".crdownload")
CANDIDATE_SUFFIXES = (".csv", ".tsv", ".txt", ".log")

PINE_HEADER_MARKERS = ("RECORD_TYPE", "SIGNAL_ID", "SCHEMA_VERSION")


@dataclass
class Classification:
    detected_type: str
    parser_name: str | None = None
    confidence: float = 0.0
    needs_review: bool = False
    error_code: str | None = None
    error_message: str | None = None
    timezone_status: str | None = None
    metadata: dict = field(default_factory=dict)


def is_ignored_name(name: str) -> bool:
    lower = name.lower()
    if name.startswith("."):
        return True
    return any(lower.endswith(suf) for suf in IGNORE_SUFFIXES)


def is_candidate_name(name: str) -> bool:
    if is_ignored_name(name):
        return False
    lower = name.lower()
    return any(lower.endswith(suf) for suf in CANDIDATE_SUFFIXES)


def _looks_like_pine(text: str) -> bool:
    header = ""
    for line in text.splitlines():
        if line.strip():
            header = line.upper()
            break
    return all(m in header for m in PINE_HEADER_MARKERS)


def detect_pine_text(text: str) -> Classification:
    if not _looks_like_pine(text):
        return Classification(
            detected_type="UNKNOWN",
            needs_review=True,
            error_code="UNKNOWN_FORMAT",
            error_message="Not a Pine signal log (missing RECORD_TYPE / SIGNAL_ID header).",
        )
    parsed = parse_pine_log(text)
    if not parsed.events and parsed.errors:
        return Classification(
            detected_type="PINE_LOG",
            parser_name="pine_signallog",
            confidence=0.4,
            needs_review=True,
            error_code="PARSER_ERROR",
            error_message="Pine log parsed with errors and no valid events.",
            metadata={"errors": parsed.errors[:5]},
        )
    return Classification(
        detected_type="PINE_LOG",
        parser_name="pine_signallog",
        confidence=1.0,
        metadata={"events": len(parsed.events), "errors": len(parsed.errors)},
    )


def classify_path(path: Path) -> Classification:
    """Classify a file by content. Does not mutate the database."""
    sha = sha256_file(str(path))
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    if _looks_like_pine(text):
        result = detect_pine_text(text)
        result.metadata["sha256"] = sha
        return result

    try:
        preview = preview_file(path)
    except TimezoneRequiredError as exc:
        return Classification(
            detected_type="UNKNOWN",
            needs_review=True,
            error_code="TIMEZONE_REQUIRED",
            error_message=str(exc),
            metadata={"sha256": sha},
        )
    except Exception as exc:
        return Classification(
            detected_type="UNKNOWN",
            needs_review=True,
            error_code="PARSER_ERROR",
            error_message=str(exc),
            metadata={"sha256": sha},
        )

    if isinstance(preview, dict) and preview.get("error"):
        return Classification(
            detected_type="UNKNOWN",
            needs_review=True,
            error_code=str(preview.get("error")),
            error_message=str(preview.get("message") or preview.get("error")),
            metadata={"sha256": sha, "detections": preview.get("detections")},
        )

    tz_status = getattr(preview, "timezone_status", None)
    if tz_status == "REQUIRES_USER_INPUT":
        return Classification(
            detected_type=_type_for_parser(preview.parser_name),
            parser_name=preview.parser_name,
            confidence=float(preview.confidence or 0),
            needs_review=True,
            error_code="TIMEZONE_REQUIRED",
            error_message="Timestamps require an explicit timezone.",
            timezone_status=tz_status,
            metadata={"sha256": sha},
        )

    parser = preview.parser_name
    return Classification(
        detected_type=_type_for_parser(parser),
        parser_name=parser,
        confidence=float(preview.confidence or 0),
        timezone_status=tz_status,
        metadata={"sha256": sha, "row_count": preview.row_count},
    )


def _type_for_parser(parser_name: str | None) -> str:
    return {
        "tradingview_manual": "ORDER_HISTORY",
        "tradingview_activity_log": "ACTIVITY_LOG",
        "tradingview_strategy": "AUTO_STRATEGY_TESTER",
        "pine_signallog": "PINE_LOG",
    }.get(parser_name or "", "UNKNOWN")


def classify_bytes_preview_only(path: Path) -> Classification:
    return classify_path(path)


def file_snapshot(path: Path) -> tuple[int, float]:
    st = path.stat()
    return st.st_size, st.st_mtime


def is_stable(path: Path, previous: tuple[int, float] | None, min_age_seconds: float | None = None) -> bool:
    if not path.exists() or not path.is_file():
        return False
    current = file_snapshot(path)
    if previous is not None and current != previous:
        return False
    age = min_age_seconds if min_age_seconds is not None else settings.file_stable_seconds
    import time

    return (time.time() - current[1]) >= age
