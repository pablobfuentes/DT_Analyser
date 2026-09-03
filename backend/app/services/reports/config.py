"""Centralized bucket thresholds for report dimensions."""

from decimal import Decimal

# Entry price buckets: (label, min inclusive, max exclusive) last uses None for max
ENTRY_PRICE_BUCKETS = [
    ("lt_2", "<$2", None, Decimal("2")),
    ("2_3", "$2–$3", Decimal("2"), Decimal("3")),
    ("3_5", "$3–$5", Decimal("3"), Decimal("5")),
    ("5_10", "$5–$10", Decimal("5"), Decimal("10")),
    ("10_20", "$10–$20", Decimal("10"), Decimal("20")),
    ("20_plus", "$20+", Decimal("20"), None),
]

QUANTITY_BUCKETS = [
    ("lt_100", "<100", None, Decimal("100")),
    ("100_199", "100–199", Decimal("100"), Decimal("200")),
    ("200_499", "200–499", Decimal("200"), Decimal("500")),
    ("500_999", "500–999", Decimal("500"), Decimal("1000")),
    ("1000_1999", "1,000–1,999", Decimal("1000"), Decimal("2000")),
    ("2000_plus", "2,000+", Decimal("2000"), None),
]

POSITION_VALUE_BUCKETS = [
    ("lt_500", "<$500", None, Decimal("500")),
    ("500_1000", "$500–$1K", Decimal("500"), Decimal("1000")),
    ("1000_2500", "$1K–$2.5K", Decimal("1000"), Decimal("2500")),
    ("2500_5000", "$2.5K–$5K", Decimal("2500"), Decimal("5000")),
    ("5000_10000", "$5K–$10K", Decimal("5000"), Decimal("10000")),
    ("10000_plus", "$10K+", Decimal("10000"), None),
]

DURATION_BUCKETS_SEC = [
    ("lt_60", "<1 min", 0, 60),
    ("1_2", "1–2 min", 60, 120),
    ("2_5", "2–5 min", 120, 300),
    ("5_10", "5–10 min", 300, 600),
    ("10_20", "10–20 min", 600, 1200),
    ("20_60", "20–60 min", 1200, 3600),
    ("60_plus", "60+ min", 3600, None),
]

DAILY_PNL_STATE_BUCKETS = [
    ("lt_neg_200", "< -$200", None, Decimal("-200")),
    ("neg_200_50", "-$200 to -$50", Decimal("-200"), Decimal("-50")),
    ("neg_50_50", "-$50 to +$50", Decimal("-50"), Decimal("50")),
    ("50_200", "+$50 to +$200", Decimal("50"), Decimal("200")),
    ("gt_200", "> +$200", Decimal("200"), None),
]

WEEKDAYS = [
    ("MON", "Monday"),
    ("TUE", "Tuesday"),
    ("WED", "Wednesday"),
    ("THU", "Thursday"),
    ("FRI", "Friday"),
    ("SAT", "Saturday"),
    ("SUN", "Sunday"),
]

MARKET_SECTION = ("MARKET", "Market", "MARKET_ENRICHMENT")
EXECUTION_SECTION = ("EXECUTION", "Execution Quality", "MFE_MAE")
STRATEGY_SECTION = ("STRATEGY", "Strategy", "PINE_SIGNALS")
RISK_SECTION = ("RISK", "Risk & R", None)

SECTIONS = [
    ("TIME", "Time", True),
    ("TRADE", "Trade Characteristics", True),
    ("INSTRUMENT", "Instrument", True),
    ("SOURCE", "Source & Direction", True),
    ("BEHAVIOR", "Trader Behavior", True),
    ("OUTCOMES", "Outcomes", True),
    ("STRATEGY", "Strategy", False, "PINE_SIGNALS"),
    ("EXECUTION", "Execution Quality", False, "MFE_MAE"),
    ("RISK", "Risk & R", False, "RISK_ANALYTICS"),
]

# Step 8 execution buckets
MFE_R_BUCKETS = [
    ("lt_0_5", "<0.5R", None, Decimal("0.5")),
    ("0_5_1", "0.5–1R", Decimal("0.5"), Decimal("1")),
    ("1_1_5", "1–1.5R", Decimal("1"), Decimal("1.5")),
    ("1_5_2", "1.5–2R", Decimal("1.5"), Decimal("2")),
    ("2_3", "2–3R", Decimal("2"), Decimal("3")),
    ("3_5", "3–5R", Decimal("3"), Decimal("5")),
    ("5_plus", "5R+", Decimal("5"), None),
]

MAE_R_BUCKETS = [
    ("lte_neg_2", "≤-2R", None, Decimal("-2")),
    ("neg_2_1_5", "-2 to -1.5R", Decimal("-2"), Decimal("-1.5")),
    ("neg_1_5_1", "-1.5 to -1R", Decimal("-1.5"), Decimal("-1")),
    ("neg_1_0_75", "-1 to -0.75R", Decimal("-1"), Decimal("-0.75")),
    ("neg_0_75_0_5", "-0.75 to -0.5R", Decimal("-0.75"), Decimal("-0.5")),
    ("neg_0_5_0_25", "-0.5 to -0.25R", Decimal("-0.5"), Decimal("-0.25")),
    ("neg_0_25_0", "-0.25 to 0R", Decimal("-0.25"), Decimal("0")),
]

EXIT_EFFICIENCY_BUCKETS = [
    ("lt_0", "<0%", None, Decimal("0")),
    ("0_25", "0–25%", Decimal("0"), Decimal("25")),
    ("25_50", "25–50%", Decimal("25"), Decimal("50")),
    ("50_75", "50–75%", Decimal("50"), Decimal("75")),
    ("75_90", "75–90%", Decimal("75"), Decimal("90")),
    ("90_100", "90–100%", Decimal("90"), Decimal("100")),
    ("gt_100", "100%+", Decimal("100"), None),
]

R_LEFT_BUCKETS = [
    ("lt_0", "<0R", None, Decimal("0")),
    ("0_0_5", "0–0.5R", Decimal("0"), Decimal("0.5")),
    ("0_5_1", "0.5–1R", Decimal("0.5"), Decimal("1")),
    ("1_2", "1–2R", Decimal("1"), Decimal("2")),
    ("2_3", "2–3R", Decimal("2"), Decimal("3")),
    ("3_plus", "3R+", Decimal("3"), None),
]

TIME_TO_MFE_BUCKETS = [
    ("lt_60", "<1 min", 0, 60),
    ("1_2", "1–2 min", 60, 120),
    ("2_5", "2–5 min", 120, 300),
    ("5_10", "5–10 min", 300, 600),
    ("10_20", "10–20 min", 600, 1200),
    ("20_60", "20–60 min", 1200, 3600),
    ("60_plus", "60+ min", 3600, None),
]

MFE_TO_EXIT_BUCKETS = [
    ("lt_60", "<1 min", 0, 60),
    ("1_2", "1–2 min", 60, 120),
    ("2_5", "2–5 min", 120, 300),
    ("5_10", "5–10 min", 300, 600),
    ("10_20", "10–20 min", 600, 1200),
    ("20_plus", "20+ min", 1200, None),
]

PEAK_GIVEBACK_BUCKETS = [
    ("lt_10", "<10%", None, Decimal("10")),
    ("10_25", "10–25%", Decimal("10"), Decimal("25")),
    ("25_50", "25–50%", Decimal("25"), Decimal("50")),
    ("50_75", "50–75%", Decimal("50"), Decimal("75")),
    ("75_100", "75–100%", Decimal("75"), Decimal("100")),
    ("gt_100", "100%+", Decimal("100"), None),
]

# Step 4 market buckets: (key, label, min inclusive, max exclusive)
GAP_BUCKETS = [
    ("lt_0", "<0%", None, Decimal("0")),
    ("0_2", "0–2%", Decimal("0"), Decimal("2")),
    ("2_5", "2–5%", Decimal("2"), Decimal("5")),
    ("5_10", "5–10%", Decimal("5"), Decimal("10")),
    ("10_20", "10–20%", Decimal("10"), Decimal("20")),
    ("20_50", "20–50%", Decimal("20"), Decimal("50")),
    ("50_100", "50–100%", Decimal("50"), Decimal("100")),
    ("100_plus", "100%+", Decimal("100"), None),
]

VOLUME_BUCKETS = [
    ("lt_500k", "<500K", None, Decimal("500000")),
    ("500k_1m", "500K–1M", Decimal("500000"), Decimal("1000000")),
    ("1m_2m", "1M–2M", Decimal("1000000"), Decimal("2000000")),
    ("2m_5m", "2M–5M", Decimal("2000000"), Decimal("5000000")),
    ("5m_10m", "5M–10M", Decimal("5000000"), Decimal("10000000")),
    ("10m_25m", "10M–25M", Decimal("10000000"), Decimal("25000000")),
    ("25m_50m", "25M–50M", Decimal("25000000"), Decimal("50000000")),
    ("50m_plus", "50M+", Decimal("50000000"), None),
]

RVOL_BUCKETS = [
    ("lt_1", "<1x", None, Decimal("1")),
    ("1_2", "1–2x", Decimal("1"), Decimal("2")),
    ("2_5", "2–5x", Decimal("2"), Decimal("5")),
    ("5_10", "5–10x", Decimal("5"), Decimal("10")),
    ("10_20", "10–20x", Decimal("10"), Decimal("20")),
    ("20_plus", "20x+", Decimal("20"), None),
]

PRIOR_RVOL_BUCKETS = RVOL_BUCKETS[:5] + [("10_plus", "10x+", Decimal("10"), None)]

MOVEMENT_BUCKETS = [
    ("lt_neg_20", "<-20%", None, Decimal("-20")),
    ("neg_20_10", "-20 to -10%", Decimal("-20"), Decimal("-10")),
    ("neg_10_5", "-10 to -5%", Decimal("-10"), Decimal("-5")),
    ("neg_5_0", "-5 to 0%", Decimal("-5"), Decimal("0")),
    ("0_5", "0 to +5%", Decimal("0"), Decimal("5")),
    ("5_10", "+5 to +10%", Decimal("5"), Decimal("10")),
    ("10_20", "+10 to +20%", Decimal("10"), Decimal("20")),
    ("20_50", "+20 to +50%", Decimal("20"), Decimal("50")),
    ("50_plus", "+50%+", Decimal("50"), None),
]

ATR_BUCKETS = [
    ("lt_0_10", "<$0.10", None, Decimal("0.10")),
    ("0_10_0_25", "$0.10–0.25", Decimal("0.10"), Decimal("0.25")),
    ("0_25_0_50", "$0.25–0.50", Decimal("0.25"), Decimal("0.50")),
    ("0_50_1", "$0.50–1", Decimal("0.50"), Decimal("1")),
    ("1_2", "$1–2", Decimal("1"), Decimal("2")),
    ("2_plus", "$2+", Decimal("2"), None),
]

ENTRY_ATR_BUCKETS = [
    ("lt_neg_100", "<-100%", None, Decimal("-100")),
    ("neg_100_50", "-100 to -50%", Decimal("-100"), Decimal("-50")),
    ("neg_50_0", "-50 to 0%", Decimal("-50"), Decimal("0")),
    ("0_50", "0–50%", Decimal("0"), Decimal("50")),
    ("50_100", "50–100%", Decimal("50"), Decimal("100")),
    ("100_150", "100–150%", Decimal("100"), Decimal("150")),
    ("150_200", "150–200%", Decimal("150"), Decimal("200")),
    ("200_plus", "200%+", Decimal("200"), None),
]

TR_ATR_BUCKETS = [
    ("lt_50", "<50%", None, Decimal("50")),
    ("50_75", "50–75%", Decimal("50"), Decimal("75")),
    ("75_100", "75–100%", Decimal("75"), Decimal("100")),
    ("100_150", "100–150%", Decimal("100"), Decimal("150")),
    ("150_200", "150–200%", Decimal("150"), Decimal("200")),
    ("200_300", "200–300%", Decimal("200"), Decimal("300")),
    ("300_plus", "300%+", Decimal("300"), None),
]

SMA_DIST_BUCKETS = MOVEMENT_BUCKETS  # same pct structure

MARKET_MOVEMENT_BUCKETS = [
    ("lt_neg_2", "<-2%", None, Decimal("-2")),
    ("neg_2_1", "-2 to -1%", Decimal("-2"), Decimal("-1")),
    ("neg_1_0_5", "-1 to -0.5%", Decimal("-1"), Decimal("-0.5")),
    ("neg_0_5_0", "-0.5 to 0%", Decimal("-0.5"), Decimal("0")),
    ("0_0_5", "0 to +0.5%", Decimal("0"), Decimal("0.5")),
    ("0_5_1", "+0.5 to +1%", Decimal("0.5"), Decimal("1")),
    ("1_2", "+1 to +2%", Decimal("1"), Decimal("2")),
    ("2_plus", "+2%+", Decimal("2"), None),
]

MARKET_GAP_BUCKETS = [
    ("lt_neg_1", "<-1%", None, Decimal("-1")),
    ("neg_1_0_5", "-1 to -0.5%", Decimal("-1"), Decimal("-0.5")),
    ("neg_0_5_0", "-0.5 to 0%", Decimal("-0.5"), Decimal("0")),
    ("0_0_5", "0 to +0.5%", Decimal("0"), Decimal("0.5")),
    ("0_5_1", "+0.5 to +1%", Decimal("0.5"), Decimal("1")),
    ("1_plus", "+1%+", Decimal("1"), None),
]

DAY_TYPE_LABELS = {
    "trend_up": "Trend Up",
    "trend_down": "Trend Down",
    "inside_range": "Inside Range",
    "outside_range": "Outside Range",
}

# Step 5 signal-time buckets — distinct keys from Step 4 instrument gap/RVOL
SIGNAL_GAP_BUCKETS = [
    ("lt_2", "<2%", None, Decimal("2")),
    ("2_5", "2–5%", Decimal("2"), Decimal("5")),
    ("5_10", "5–10%", Decimal("5"), Decimal("10")),
    ("10_20", "10–20%", Decimal("10"), Decimal("20")),
    ("20_50", "20–50%", Decimal("20"), Decimal("50")),
    ("50_100", "50–100%", Decimal("50"), Decimal("100")),
    ("100_plus", "100%+", Decimal("100"), None),
]

SIGNAL_RVOL_BUCKETS = [
    ("lt_2", "<2x", None, Decimal("2")),
    ("2_5", "2–5x", Decimal("2"), Decimal("5")),
    ("5_10", "5–10x", Decimal("5"), Decimal("10")),
    ("10_20", "10–20x", Decimal("10"), Decimal("20")),
    ("20_plus", "20x+", Decimal("20"), None),
]

IMPULSE_BUCKETS = [
    ("lt_4", "<4%", None, Decimal("4")),
    ("4_5", "4–5%", Decimal("4"), Decimal("5")),
    ("5_7_5", "5–7.5%", Decimal("5"), Decimal("7.5")),
    ("7_5_10", "7.5–10%", Decimal("7.5"), Decimal("10")),
    ("10_15", "10–15%", Decimal("10"), Decimal("15")),
    ("15_25", "15–25%", Decimal("15"), Decimal("25")),
    ("25_plus", "25%+", Decimal("25"), None),
]

RETRACEMENT_BUCKETS = [
    ("lt_20", "<20%", None, Decimal("20")),
    ("20_30", "20–30%", Decimal("20"), Decimal("30")),
    ("30_40", "30–40%", Decimal("30"), Decimal("40")),
    ("40_50", "40–50%", Decimal("40"), Decimal("50")),
    ("50_plus", "50%+", Decimal("50"), None),
]

PLANNED_EXPOSURE_BUCKETS = [
    ("lt_2", "<2%", None, Decimal("2")),
    ("2_5", "2–5%", Decimal("2"), Decimal("5")),
    ("5_10", "5–10%", Decimal("5"), Decimal("10")),
    ("10_20", "10–20%", Decimal("10"), Decimal("20")),
    ("20_plus", "20%+", Decimal("20"), None),
]

# Step 7 risk buckets — inclusive lo, exclusive hi; last bucket open
INITIAL_RISK_BUCKETS = [
    ("lt_25", "<$25", None, Decimal("25")),
    ("25_50", "$25–$50", Decimal("25"), Decimal("50")),
    ("50_100", "$50–$100", Decimal("50"), Decimal("100")),
    ("100_200", "$100–$200", Decimal("100"), Decimal("200")),
    ("200_500", "$200–$500", Decimal("200"), Decimal("500")),
    ("500_plus", "$500+", Decimal("500"), None),
]

RISK_PCT_EQUITY_BUCKETS = [
    ("lt_0_25", "<0.25%", None, Decimal("0.25")),
    ("0_25_0_50", "0.25–0.50%", Decimal("0.25"), Decimal("0.50")),
    ("0_50_0_75", "0.50–0.75%", Decimal("0.50"), Decimal("0.75")),
    ("0_75_1_00", "0.75–1.00%", Decimal("0.75"), Decimal("1.00")),
    ("1_00_1_50", "1.00–1.50%", Decimal("1.00"), Decimal("1.50")),
    ("1_50_2_00", "1.50–2.00%", Decimal("1.50"), Decimal("2.00")),
    ("2_00_plus", "2.00%+", Decimal("2.00"), None),
]

STOP_DISTANCE_BUCKETS = [
    ("lt_1", "<1%", None, Decimal("1")),
    ("1_2", "1–2%", Decimal("1"), Decimal("2")),
    ("2_3", "2–3%", Decimal("2"), Decimal("3")),
    ("3_5", "3–5%", Decimal("3"), Decimal("5")),
    ("5_7_5", "5–7.5%", Decimal("5"), Decimal("7.5")),
    ("7_5_10", "7.5–10%", Decimal("7.5"), Decimal("10")),
    ("10_plus", "10%+", Decimal("10"), None),
]

_BUCKET_REGISTRY = {
    "gap": GAP_BUCKETS,
    "volume": VOLUME_BUCKETS,
    "rvol": RVOL_BUCKETS,
    "prior_rvol": PRIOR_RVOL_BUCKETS,
    "movement": MOVEMENT_BUCKETS,
    "atr": ATR_BUCKETS,
    "entry_atr": ENTRY_ATR_BUCKETS,
    "tr_atr": TR_ATR_BUCKETS,
    "sma_dist": SMA_DIST_BUCKETS,
    "market_movement": MARKET_MOVEMENT_BUCKETS,
    "market_gap": MARKET_GAP_BUCKETS,
    "signal_gap": SIGNAL_GAP_BUCKETS,
    "signal_rvol": SIGNAL_RVOL_BUCKETS,
    "impulse": IMPULSE_BUCKETS,
    "retracement": RETRACEMENT_BUCKETS,
    "planned_exposure": PLANNED_EXPOSURE_BUCKETS,
    "quantity": QUANTITY_BUCKETS,
    "position_value": POSITION_VALUE_BUCKETS,
    "initial_risk": INITIAL_RISK_BUCKETS,
    "risk_pct_equity": RISK_PCT_EQUITY_BUCKETS,
    "stop_distance": STOP_DISTANCE_BUCKETS,
}


def bucket_key_for_value(kind: str, value: Decimal) -> str:
    buckets = _BUCKET_REGISTRY.get(kind, [])
    for key, _label, lo, hi in buckets:
        if lo is not None and value < lo:
            continue
        if hi is not None and value >= hi:
            continue
        return key
    return buckets[-1][0] if buckets else "unknown"
