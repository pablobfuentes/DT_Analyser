import logging
from pathlib import Path

import polars as pl

from app.config import settings
from app.importers.base import DetectionResult, PreviewResult
from app.importers.base_parser import read_csv
from app.importers.tradingview_activity_log import TradingViewActivityLogParser
from app.importers.tradingview_manual import TradingViewManualParser
from app.importers.tradingview_strategy import TradingViewStrategyParser

logger = logging.getLogger(__name__)

PARSERS = [
    TradingViewStrategyParser(),
    TradingViewActivityLogParser(),
    TradingViewManualParser(),
]


def detect_format(df: pl.DataFrame) -> list[DetectionResult]:
    results = [p.can_parse(df) for p in PARSERS]
    return sorted(results, key=lambda r: r.confidence, reverse=True)


def get_parser(name: str):
    for p in PARSERS:
        if p.name == name:
            return p
    return None


def detect_file(path: str | Path) -> tuple[pl.DataFrame, list[DetectionResult]]:
    df = read_csv(path)
    return df, detect_format(df)


def preview_file(
    path: str | Path,
    parser_name: str | None = None,
    timezone: str | None = None,
) -> PreviewResult | dict:
    df, detections = detect_file(path)
    best = detections[0] if detections else None

    if parser_name:
        parser = get_parser(parser_name)
        if not parser:
            return {"error": "UNKNOWN_PARSER", "message": f"Parser {parser_name} not found"}
    else:
        if not best or best.confidence < settings.parser_confidence_threshold:
            return {
                "error": "UNKNOWN_FORMAT",
                "message": "Could not identify CSV format with sufficient confidence.",
                "detected_columns": df.columns,
                "detections": [
                    {
                        "parser": d.parser_name,
                        "confidence": d.confidence,
                        "missing_fields": d.missing_fields,
                    }
                    for d in detections
                ],
            }
        runner_up = detections[1] if len(detections) > 1 else None
        if (
            runner_up
            and runner_up.confidence >= settings.parser_confidence_threshold
            and (best.confidence - runner_up.confidence) < settings.parser_ambiguous_margin
        ):
            return {
                "error": "AMBIGUOUS_FORMAT",
                "message": "Multiple parsers matched with similar confidence; select a parser.",
                "detected_columns": df.columns,
                "options": [
                    d.parser_name
                    for d in detections
                    if d.confidence >= settings.parser_confidence_threshold
                ],
                "detections": [
                    {
                        "parser": d.parser_name,
                        "confidence": d.confidence,
                        "missing_fields": d.missing_fields,
                    }
                    for d in detections
                ],
            }
        parser = get_parser(best.parser_name)

    assert parser is not None
    return parser.preview(df, timezone, settings.preview_sample_size)
