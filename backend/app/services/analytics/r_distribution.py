"""R-multiple distribution buckets."""

from __future__ import annotations

from decimal import Decimal

from app.utils.analytics import decimal_str

R_BUCKETS = [
    ("lt_-2", Decimal("-999999"), Decimal("-2"), "< -2R"),
    ("-2_to_-1.5", Decimal("-2"), Decimal("-1.5"), "-2R to -1.5R"),
    ("-1.5_to_-1", Decimal("-1.5"), Decimal("-1"), "-1.5R to -1R"),
    ("-1_to_-0.5", Decimal("-1"), Decimal("-0.5"), "-1R to -0.5R"),
    ("-0.5_to_0", Decimal("-0.5"), Decimal("0"), "-0.5R to 0R"),
    ("0_to_0.5", Decimal("0"), Decimal("0.5"), "0R to +0.5R"),
    ("0.5_to_1", Decimal("0.5"), Decimal("1"), "+0.5R to +1R"),
    ("1_to_1.5", Decimal("1"), Decimal("1.5"), "+1R to +1.5R"),
    ("1.5_to_2", Decimal("1.5"), Decimal("2"), "+1.5R to +2R"),
    ("2_to_3", Decimal("2"), Decimal("3"), "+2R to +3R"),
    ("gt_3", Decimal("3"), Decimal("999999"), "> +3R"),
]


def classify_r(r: Decimal) -> str:
    for key, lo, hi, _ in R_BUCKETS:
        if key == "lt_-2":
            if r < hi:
                return key
        elif key == "gt_3":
            if r >= lo:
                return key
        elif lo <= r < hi:
            return key
    return "gt_3"


def r_distribution(r_values: list[Decimal]) -> list[dict]:
    counts = {key: 0 for key, _, _, _ in R_BUCKETS}
    for r in r_values:
        counts[classify_r(r)] += 1

    total = len(r_values)
    result = []
    for key, _, _, label in R_BUCKETS:
        c = counts[key]
        pct = (Decimal(c) / Decimal(total) * Decimal("100")) if total else None
        result.append(
            {
                "bucket": key,
                "label": label,
                "count": c,
                "pct": decimal_str(pct),
            }
        )
    return result
