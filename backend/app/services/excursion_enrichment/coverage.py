"""Excursion coverage and boundary diagnostics."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from statistics import median

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.market_data import MarketIntradayBar, TradeExcursion
from app.db.models.trade import Trade
from app.market_data.cache_intraday import count_intraday_bars, count_unique_symbol_days
from app.services.excursion_enrichment.config import CALCULATION_VERSION


def get_excursion_coverage(db: Session) -> dict:
    total_closed = db.query(Trade).filter(Trade.status == "CLOSED").count()
    enriched = (
        db.query(TradeExcursion)
        .filter(TradeExcursion.quality_status.notin_(["PENDING", "OPEN_TRADE"]))
        .count()
    )
    r_qualified = (
        db.query(TradeExcursion)
        .filter(TradeExcursion.mfe_r.isnot(None))
        .count()
    )
    consolidated = db.query(TradeExcursion).filter(TradeExcursion.is_consolidated == True).count()
    partial = db.query(TradeExcursion).filter(TradeExcursion.is_consolidated == False).count()
    boundary = db.query(TradeExcursion).filter(TradeExcursion.boundary_ambiguity == True).count()
    sparse = db.query(TradeExcursion).filter(TradeExcursion.sparse_interval == True).count()
    missing = total_closed - enriched

    return {
        "total_closed_trades": total_closed,
        "excursion_enriched": enriched,
        "excursion_coverage_pct": _pct(enriched, total_closed),
        "r_qualified_excursions": r_qualified,
        "mfe_r_coverage_pct": _pct(r_qualified, total_closed),
        "consolidated_count": consolidated,
        "partial_feed_count": partial,
        "boundary_ambiguous_count": boundary,
        "sparse_interval_count": sparse,
        "missing_count": missing,
        "copilot_exit_available": 0,
        "copilot_coverage_pct": None,
        "copilot_status": "UNAVAILABLE — Step 5 signal tables not present in database",
        "intraday_bars_cached": count_intraday_bars(db),
        "unique_symbol_days": _unique_symbol_days(db),
    }


def boundary_spread_stats(db: Session) -> dict:
    spreads_r = [
        float(r.mfe_boundary_spread_r)
        for r in db.query(TradeExcursion).filter(TradeExcursion.mfe_boundary_spread_r.isnot(None)).all()
        if r.mfe_boundary_spread_r is not None
    ]
    spreads_amt = [
        float(r.mfe_boundary_spread_amount)
        for r in db.query(TradeExcursion).filter(TradeExcursion.mfe_boundary_spread_amount.isnot(None)).all()
        if r.mfe_boundary_spread_amount is not None
    ]
    if not spreads_r:
        return {
            "avg_mfe_spread_amount": None,
            "avg_mfe_spread_r": None,
            "median_mfe_spread_r": None,
            "p95_mfe_spread_r": None,
            "count_spread_gt_025r": 0,
            "count_spread_gt_050r": 0,
        }
    sorted_r = sorted(spreads_r)
    p95_idx = min(len(sorted_r) - 1, int(len(sorted_r) * 0.95))
    return {
        "avg_mfe_spread_amount": sum(spreads_amt) / len(spreads_amt) if spreads_amt else None,
        "avg_mfe_spread_r": sum(spreads_r) / len(spreads_r),
        "median_mfe_spread_r": median(spreads_r),
        "p95_mfe_spread_r": sorted_r[p95_idx],
        "count_spread_gt_025r": sum(1 for x in spreads_r if x > 0.25),
        "count_spread_gt_050r": sum(1 for x in spreads_r if x > 0.50),
    }


def storage_stats(db: Session) -> dict:
    db_path = settings.database_url.replace("sqlite:///", "")
    size_bytes = os.path.getsize(db_path) if os.path.isfile(db_path) else 0
    bar_count = count_intraday_bars(db)
    sym_days = _unique_symbol_days(db)
    avg_bars = bar_count / sym_days if sym_days else 0
    advisory = None
    if size_bytes >= 2_000_000_000:
        advisory = "strong"
    elif size_bytes >= 1_000_000_000:
        advisory = "moderate"
    return {
        "database_size_bytes": size_bytes,
        "database_size_mb": round(size_bytes / 1_048_576, 2),
        "intraday_bar_count": bar_count,
        "unique_symbol_days": sym_days,
        "avg_bars_per_symbol_day": round(avg_bars, 1),
        "storage_advisory": advisory,
    }


def _unique_symbol_days(db: Session) -> int:
    rows = db.query(MarketIntradayBar.symbol, func.date(MarketIntradayBar.bar_time_utc)).distinct().all()
    return len(rows)


def _pct(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return round(num / den * 100, 1)
