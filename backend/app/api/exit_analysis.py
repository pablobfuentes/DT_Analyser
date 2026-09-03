"""Exit Analyzer API (Step 8)."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.models.market_data import TradeExcursion
from app.db.models.trade import Trade
from app.db.session import get_db
from app.services.dashboard_service import DashboardFilters, build_closed_trades_query
from app.services.excursion_enrichment.config import BEST_CAPTURE_MIN_MFE_R
from app.services.excursion_enrichment.coverage import get_excursion_coverage
from app.utils.analytics import decimal_str

router = APIRouter(prefix="/api/exit-analysis", tags=["exit-analysis"])


@router.get("")
def exit_analysis(
    db: Session = Depends(get_db),
    start_date: str | None = None,
    end_date: str | None = None,
    account_id: int | None = None,
    source_type: str | None = None,
    direction: str | None = None,
    ticker: str | None = None,
):
    from datetime import date

    filt = DashboardFilters()
    if start_date:
        filt.start_date = date.fromisoformat(start_date)
    if end_date:
        filt.end_date = date.fromisoformat(end_date)
    filt.account_id = account_id
    filt.source_type = source_type
    filt.direction = direction
    filt.ticker = ticker

    trades = build_closed_trades_query(db, filt).all()
    trade_ids = [t.id for t in trades]
    if not trade_ids:
        return _empty_summary(db)

    exc_rows = db.query(TradeExcursion).filter(TradeExcursion.trade_id.in_(trade_ids)).all()
    exc_by_id = {e.trade_id: e for e in exc_rows}

    mfe_rs, mae_rs, effs, r_lefts, givebacks, mfe_times = [], [], [], [], [], []
    capture_25 = capture_50 = capture_75 = capture_90 = 0
    eff_defined = 0
    pos_mfe_to_loss = 0
    reached_2r_closed_lt_1r = 0
    reached_2r_closed_losing = 0

    for t in trades:
        e = exc_by_id.get(t.id)
        if not e or e.quality_status in ("PENDING", "NO_INTRADAY_DATA", "OPEN_TRADE"):
            continue
        if e.mfe_r is not None:
            mfe_rs.append(e.mfe_r)
        if e.mae_r is not None:
            mae_rs.append(e.mae_r)
        if e.exit_efficiency_pct is not None:
            eff = e.exit_efficiency_pct
            effs.append(eff)
            eff_defined += 1
            if eff >= 25:
                capture_25 += 1
            if eff >= 50:
                capture_50 += 1
            if eff >= 75:
                capture_75 += 1
            if eff >= 90:
                capture_90 += 1
        if e.r_left_on_table is not None:
            r_lefts.append(e.r_left_on_table)
        if e.peak_giveback_pct is not None:
            givebacks.append(e.peak_giveback_pct)
        if e.time_to_mfe_seconds is not None:
            mfe_times.append(e.time_to_mfe_seconds)
        if e.position_mfe_amount and e.position_mfe_amount > 0 and e.gross_realized_pnl is not None and e.gross_realized_pnl < 0:
            pos_mfe_to_loss += 1
        if e.mfe_r is not None and e.mfe_r >= Decimal("2"):
            if e.gross_realized_r is not None and e.gross_realized_r < Decimal("1"):
                reached_2r_closed_lt_1r += 1
            if e.gross_realized_pnl is not None and e.gross_realized_pnl < 0:
                reached_2r_closed_losing += 1

    def avg(vals):
        return decimal_str(sum(vals, Decimal("0")) / Decimal(len(vals))) if vals else None

    def median(vals):
        if not vals:
            return None
        s = sorted(vals)
        n = len(s)
        mid = n // 2
        if n % 2:
            return decimal_str(s[mid])
        return decimal_str((s[mid - 1] + s[mid]) / Decimal("2"))

    worst_left = sorted(
        [e for e in exc_rows if e.r_left_on_table is not None],
        key=lambda x: x.r_left_on_table,
        reverse=True,
    )[:20]

    worst_giveback = sorted(
        [e for e in exc_rows if e.peak_giveback_r is not None],
        key=lambda x: x.peak_giveback_r,
        reverse=True,
    )[:20]

    best_capture = sorted(
        [
            e
            for e in exc_rows
            if e.exit_efficiency_pct is not None
            and e.mfe_r is not None
            and e.mfe_r >= BEST_CAPTURE_MIN_MFE_R
            and e.position_mfe_amount
            and e.position_mfe_amount > 0
        ],
        key=lambda x: x.exit_efficiency_pct,
        reverse=True,
    )[:20]

    scatter = [
        {
            "trade_id": e.trade_id,
            "mfe_r": decimal_str(e.mfe_r),
            "mae_r": decimal_str(e.mae_r) if e.mae_r is not None else None,
            "actual_r": decimal_str(e.gross_realized_r),
            "ticker": next((t.ticker for t in trades if t.id == e.trade_id), ""),
        }
        for e in exc_rows
        if e.mfe_r is not None and e.gross_realized_r is not None
    ]

    cov = get_excursion_coverage(db)

    return {
        "summary": {
            "average_mfe_r": avg(mfe_rs),
            "average_mae_r": avg(mae_rs),
            "average_exit_efficiency": avg(effs),
            "median_exit_efficiency": median(effs),
            "average_r_left_on_table": avg(r_lefts),
            "average_peak_giveback_pct": avg(givebacks),
            "median_time_to_mfe_seconds": median([Decimal(t) for t in mfe_times]) if mfe_times else None,
            "capture_ge_25_pct": _pct(capture_25, eff_defined),
            "capture_ge_50_pct": _pct(capture_50, eff_defined),
            "capture_ge_75_pct": _pct(capture_75, eff_defined),
            "capture_ge_90_pct": _pct(capture_90, eff_defined),
            "positive_mfe_to_loss_count": pos_mfe_to_loss,
            "positive_mfe_to_loss_pct": _pct(pos_mfe_to_loss, len(exc_rows)),
            "reached_2r_closed_lt_1r": reached_2r_closed_lt_1r,
            "reached_2r_closed_losing": reached_2r_closed_losing,
            "best_capture_min_mfe_r": str(BEST_CAPTURE_MIN_MFE_R),
        },
        "coverage": cov,
        "scatter": scatter,
        "worst_left_on_table": [_table_row(db, e) for e in worst_left],
        "worst_giveback": [_table_row(db, e) for e in worst_giveback],
        "best_capture": [_table_row(db, e) for e in best_capture],
    }


def _table_row(db: Session, e: TradeExcursion) -> dict:
    t = db.get(Trade, e.trade_id)
    return {
        "trade_id": e.trade_id,
        "ticker": t.ticker if t else "",
        "exit_date": t.exit_time_utc.date().isoformat() if t and t.exit_time_utc else None,
        "actual_r": decimal_str(e.gross_realized_r),
        "mfe_r": decimal_str(e.mfe_r),
        "mae_r": decimal_str(e.mae_r),
        "r_left_on_table": decimal_str(e.r_left_on_table),
        "exit_efficiency_pct": decimal_str(e.exit_efficiency_pct),
        "peak_giveback_r": decimal_str(e.peak_giveback_r),
        "peak_giveback_pct": decimal_str(e.peak_giveback_pct),
        "mfe_to_exit_seconds": e.mfe_to_exit_seconds,
        "quality_status": e.quality_status,
    }


def _pct(num: int, den: int) -> float | None:
    if den == 0:
        return None
    return round(num / den * 100, 1)


def _empty_summary(db: Session) -> dict:
    return {
        "summary": {},
        "coverage": get_excursion_coverage(db),
        "scatter": [],
        "worst_left_on_table": [],
        "worst_giveback": [],
        "best_capture": [],
    }
