from app.importers.detector import detect_file, preview_file
from tests.conftest import fixture_path


def test_detect_manual_format():
    _, detections = detect_file(fixture_path("simple_long.csv"))
    assert detections[0].parser_name == "tradingview_manual"
    assert detections[0].confidence >= 0.5


def test_detect_strategy_format():
    _, detections = detect_file(fixture_path("strategy_tester.csv"))
    assert detections[0].parser_name == "tradingview_strategy"
    assert detections[0].confidence >= 0.5


def test_unknown_format():
    result = preview_file(fixture_path("unknown.csv"))
    assert isinstance(result, dict)
    assert result["error"] == "UNKNOWN_FORMAT"


def test_missing_field_detection():
    _, detections = detect_file(fixture_path("missing_field.csv"))
    manual = next(d for d in detections if d.parser_name == "tradingview_manual")
    assert "price" in manual.missing_fields


def test_no_timezone_status():
    result = preview_file(fixture_path("no_timezone.csv"), parser_name="tradingview_manual")
    assert result.timezone_status == "REQUIRES_USER_INPUT"
