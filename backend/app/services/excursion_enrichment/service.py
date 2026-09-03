"""Excursion enrichment orchestration."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.execution import Execution
from app.db.models.market_data import ExcursionEnrichmentJob, TradeExcursion
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.market_data.base import MarketDataProvider
from app.market_data.cache_intraday import (
    load_cached_intraday,
    ny_session_bounds_utc,
    session_fully_cached,
    store_intraday_bars,
)
from app.market_data.models import FetchStats, IntradayBar
from app.market_data.registry import get_market_data_provider
from app.services.excursion_enrichment.calculator import CopilotExitInfo, build_excursion_record
from app.services.excursion_enrichment.config import CALCULATION_VERSION, INTRADAY_TIMEFRAME
from app.services.excursion_enrichment.replay import holding_bounds, load_exec_events, replay_excursions
from app.utils.analytics import ny_date_from_utc

logger = logging.getLogger(__name__)


def _copilot_for_trade(db: Session, trade: Trade) -> CopilotExitInfo | None:
    """Step 5 audit: signal tables not present in repo — returns None until implemented."""
    # When signals/trade_signal_links exist, load mechanical exit here.
    return None


def _symbol_days_for_trade(hold_start: datetime, hold_end: datetime) -> set[date]:
    days: set[date] = set()
    d = ny_date_from_utc(hold_start)
    end_d = ny_date_from_utc(hold_end)
    while d <= end_d:
        days.add(d)
        d += timedelta(days=1)
    return days


class ExcursionEnrichmentService:
    def __init__(self, db: Session, provider: MarketDataProvider | None = None):
        self.db = db
        self.provider = provider or get_market_data_provider(force_fake=settings.market_data_provider == "fake")
        self.stats = FetchStats()
        self.adjustment = settings.market_adjustment_mode

    def enrich(self, scope: str = "missing", dry_run: bool = False, recalculate: bool = False) -> dict:
        self.stats = FetchStats()
        job = ExcursionEnrichmentJob(
            provider=getattr(self.provider, "provider_name", "NONE"),
            feed=getattr(self.provider, "feed_name", "none"),
            status="RUNNING",
        )
        if not dry_run:
            self.db.add(job)
            self.db.flush()

        trades = self._trades_for_scope(scope, recalculate)
        job.trades_requested = len(trades)
        if not trades:
            job.status = "SUCCESS"
            job.completed_at = datetime.now(timezone.utc)
            if not dry_run:
                self.db.commit()
            return self._summary(job, dry_run)

        symbol_days: dict[str, set[date]] = {}
        for t in trades:
            links = self._load_links(t.id)
            if not links:
                continue
            try:
                events = load_exec_events(links)
                hs, he = holding_bounds(events)
            except ValueError:
                continue
            for d in _symbol_days_for_trade(hs, he):
                symbol_days.setdefault(t.ticker.upper(), set()).add(d)

        job.symbol_days_requested = sum(len(v) for v in symbol_days.values())

        if dry_run:
            return {
                **self._summary(job, True),
                "symbol_days": {k: sorted(d.isoformat() for d in v) for k, v in symbol_days.items()},
                "trades": len(trades),
            }

        # Fetch/cache symbol-days
        for sym, days in symbol_days.items():
            for d in sorted(days):
                if session_fully_cached(
                    self.db,
                    sym,
                    d,
                    self.provider.provider_name,
                    self.provider.feed_name,
                    self.adjustment,
                ):
                    self.stats.cache_hits += 1
                    continue
                start, end = ny_session_bounds_utc(d)
                cached = load_cached_intraday(
                    self.db, sym, start, end,
                    self.provider.provider_name,
                    self.provider.feed_name,
                    self.adjustment,
                )
                if cached:
                    self.stats.cache_hits += 1
                    continue
                if hasattr(self.provider, "get_intraday_bars"):
                    fetched = self.provider.get_intraday_bars(
                        [sym], start, end, INTRADAY_TIMEFRAME, self.adjustment, self.stats,
                    )
                    if fetched:
                        store_intraday_bars(
                            self.db, fetched, store_raw=settings.intraday_store_raw_payload,
                        )
                        job.bars_fetched += len(fetched)

        # Calculate per trade
        for t in trades:
            try:
                ok = self._calculate_trade(t, recalculate=recalculate)
                if ok:
                    job.success_count += 1
                else:
                    job.missing_count += 1
            except Exception as e:
                logger.exception("Excursion failed trade_id=%s: %s", t.id, e)
                job.error_count += 1

        job.provider_requests = self.stats.provider_requests
        job.cache_hits = self.stats.cache_hits
        job.status = "PARTIAL" if job.error_count else "SUCCESS"
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        return self._summary(job, False)

    def recalculate(self) -> dict:
        return self.enrich(scope="all", recalculate=True)

    def _trades_for_scope(self, scope: str, recalculate: bool) -> list[Trade]:
        q = self.db.query(Trade).filter(Trade.status == "CLOSED", Trade.exit_time_utc.isnot(None))
        if scope == "missing" and not recalculate:
            enriched_ids = self.db.query(TradeExcursion.trade_id).filter(
                TradeExcursion.calculation_version == CALCULATION_VERSION,
                TradeExcursion.quality_status != "PENDING",
            )
            q = q.filter(~Trade.id.in_(enriched_ids))
        return q.order_by(Trade.exit_time_utc.asc()).all()

    def _load_links(self, trade_id: int) -> list[tuple[TradeExecution, Execution]]:
        rows = self.db.query(TradeExecution).filter(TradeExecution.trade_id == trade_id).all()
        if not rows:
            return []
        execs = {
            e.id: e
            for e in self.db.query(Execution).filter(Execution.id.in_([r.execution_id for r in rows])).all()
        }
        return [(r, execs[r.execution_id]) for r in rows if r.execution_id in execs]

    def _bars_for_trade(self, trade: Trade, hold_start: datetime, hold_end: datetime) -> tuple[list[IntradayBar], list[IntradayBar], bool]:
        all_bars: list[IntradayBar] = []
        post_bars: list[IntradayBar] = []
        provider_missing = False
        for d in _symbol_days_for_trade(hold_start, hold_end):
            start, end = ny_session_bounds_utc(d)
            cached = load_cached_intraday(
                self.db,
                trade.ticker,
                start,
                end + timedelta(minutes=30),
                self.provider.provider_name,
                self.provider.feed_name,
                self.adjustment,
            )
            if not cached:
                provider_missing = True
            all_bars.extend(cached)
        hold_end_ext = hold_end + timedelta(minutes=30)
        post_bars = [b for b in all_bars if b.bar_time_utc >= hold_end and b.bar_time_utc <= hold_end_ext]
        hold_bars = [b for b in all_bars if b.bar_time_utc < hold_end + timedelta(minutes=1)]
        return hold_bars, post_bars, provider_missing

    def _calculate_trade(self, trade: Trade, recalculate: bool = False) -> bool:
        links = self._load_links(trade.id)
        if not links:
            return False
        events = load_exec_events(links)
        hold_start, hold_end = holding_bounds(events)
        bars, post_bars, provider_missing = self._bars_for_trade(trade, hold_start, hold_end)

        track, state, diag = replay_excursions(trade, events, bars, post_exit_bars=post_bars)
        risk = trade.initial_risk_amount
        copilot = _copilot_for_trade(self.db, trade)

        rec = build_excursion_record(
            trade,
            track,
            state,
            diag,
            holding_start=hold_start,
            holding_end=hold_end,
            provider=self.provider.provider_name,
            feed=self.provider.feed_name,
            is_consolidated=self.provider.is_consolidated,
            initial_risk=risk,
            copilot=copilot,
            provider_missing=provider_missing,
        )

        existing = self.db.query(TradeExcursion).filter(TradeExcursion.trade_id == trade.id).first()
        if existing:
            for col in TradeExcursion.__table__.columns:
                if col.name not in ("id", "trade_id"):
                    setattr(existing, col.name, getattr(rec, col.name))
        else:
            self.db.add(rec)
        self.db.flush()
        return rec.quality_status != "NO_INTRADAY_DATA"

    def _summary(self, job: ExcursionEnrichmentJob, dry_run: bool) -> dict:
        return {
            "dry_run": dry_run,
            "status": job.status,
            "trades_requested": job.trades_requested,
            "symbol_days_requested": job.symbol_days_requested,
            "bars_fetched": job.bars_fetched,
            "cache_hits": job.cache_hits,
            "provider_requests": job.provider_requests,
            "success_count": job.success_count,
            "missing_count": job.missing_count,
            "error_count": job.error_count,
        }
