"""Risk / R features for Graphs. Uses trade_risk when present; else Trade cache."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.risk import TradeRisk
from app.services.analytics.r_distribution import classify_r
from app.services.reports.config import bucket_key_for_value
from app.services.reports.features import AnnotatedTrade
from app.services.risk.service import equity_before_entry_map


def apply_risk_features(db: Session, annotated: list[AnnotatedTrade]) -> None:
    if not annotated:
        return
    ids = [at.trade.id for at in annotated]
    rows = {r.trade_id: r for r in db.query(TradeRisk).filter(TradeRisk.trade_id.in_(ids)).all()}
    need_eq = []
    for at in annotated:
        row = rows.get(at.trade.id)
        amount = row.actual_initial_risk_amount if row else at.trade.initial_risk_amount
        if amount and (row is None or row.risk_pct_equity_at_entry is None):
            need_eq.append(at.trade)
    eq_map = equity_before_entry_map(db, need_eq) if need_eq else {}

    for at in annotated:
        t = at.trade
        row = rows.get(t.id)
        r_val = (row.r_multiple if row and row.r_multiple is not None else t.r_multiple)
        amount = row.actual_initial_risk_amount if row else t.initial_risk_amount
        stop = row.initial_stop_price if row else t.initial_stop_price
        risk_pct = row.risk_pct_equity_at_entry if row else None
        if risk_pct is None and amount and eq_map.get(t.id) and eq_map[t.id] > 0:
            risk_pct = (amount / eq_map[t.id]) * Decimal("100")

        if r_val is not None:
            at.features["r_outcome_bucket"] = classify_r(r_val)
            at.features["_r_qualified"] = "true"
        else:
            at.features["_skip_r_outcome_bucket"] = "MISSING_R"
            at.features["_r_qualified"] = "false"

        if amount is not None:
            at.features["initial_risk_bucket"] = bucket_key_for_value("initial_risk", amount)
        else:
            at.features["_skip_initial_risk_bucket"] = "MISSING_RISK"

        if risk_pct is not None:
            at.features["risk_pct_equity_bucket"] = bucket_key_for_value("risk_pct_equity", risk_pct)
        else:
            at.features["_skip_risk_pct_equity_bucket"] = "MISSING_EQUITY_OR_RISK"

        if stop is not None and t.avg_entry_price and t.avg_entry_price != 0:
            from app.services.analytics.risk import risk_per_share_from_stop, validate_stop_for_direction

            if not validate_stop_for_direction(t.direction, t.avg_entry_price, stop):
                rps = risk_per_share_from_stop(t.direction, t.avg_entry_price, stop)
                dist = (rps / t.avg_entry_price) * Decimal("100")
                at.features["stop_distance_pct_bucket"] = bucket_key_for_value("stop_distance", dist)
            else:
                at.features["_skip_stop_distance_pct_bucket"] = "INVALID_STOP"
        else:
            at.features["_skip_stop_distance_pct_bucket"] = "MISSING_STOP"
