"""Market enrichment orchestration."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.market_data import InstrumentDayFeature, MarketEnrichmentJob, TradeMarketFeature
from app.db.models.trade import Trade
from app.market_data.cache import load_cached_bars, load_probed_range, mark_probed, missing_date_ranges, store_bars
from app.market_data.models import FetchStats
from app.market_data.registry import get_market_data_provider
from app.services.market_enrichment.calculator import (
    CALCULATION_VERSION,
    DayFeatureResult,
    SessionBar,
    compute_day_features,
    entry_vs_atr_pct,
    entry_vs_sma_pct,
)
from app.utils.analytics import ny_date_from_utc, ny_regular_session_complete
from app.utils.clock import utc_now

logger = logging.getLogger(__name__)

MIN_RVOL_PRIOR_SESSIONS = 50
EXTENDED_LOOKBACK_DAYS = 365


def _sessions_from_bars(bars) -> list[SessionBar]:
    return [
        SessionBar(
            trading_date=b.trading_date,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for b in sorted(bars, key=lambda x: x.trading_date)
    ]


def _persist_day_feature(
    db: Session,
    symbol: str,
    trading_date: date,
    feat: DayFeatureResult,
    provider: str,
    feed: str,
    adjustment_mode: str,
    calculation_version: str = CALCULATION_VERSION,
) -> InstrumentDayFeature:
    td = trading_date.isoformat()
    row = (
        db.query(InstrumentDayFeature)
        .filter(
            InstrumentDayFeature.symbol == symbol.upper(),
            InstrumentDayFeature.trading_date == td,
            InstrumentDayFeature.provider == provider,
            InstrumentDayFeature.feed == feed,
            InstrumentDayFeature.adjustment_mode == adjustment_mode,
            InstrumentDayFeature.calculation_version == calculation_version,
        )
        .first()
    )
    if not row:
        row = InstrumentDayFeature(
            symbol=symbol.upper(),
            trading_date=td,
            calculation_version=calculation_version,
            provider=provider,
            feed=feed,
            adjustment_mode=adjustment_mode,
        )
        db.add(row)
    row.prior_close = feat.prior_close
    row.day_open = feat.day_open
    row.day_high = feat.day_high
    row.day_low = feat.day_low
    row.day_close = feat.day_close
    row.day_volume = feat.day_volume
    row.opening_gap_pct = feat.opening_gap_pct
    row.daily_movement_pct = feat.daily_movement_pct
    row.rvol50_multiple = feat.rvol50_multiple
    row.prior_day_rvol50_multiple = feat.prior_day_rvol50_multiple
    row.true_range = feat.true_range
    row.atr14_prior = feat.atr14_prior
    row.relative_volatility_pct = feat.relative_volatility_pct
    row.sma20_prior = feat.sma20_prior
    row.sma50_prior = feat.sma50_prior
    row.day_type = feat.day_type
    row.quality_status = str(feat.quality_status)
    row.quality_flags = json.dumps(feat.quality_flags) if feat.quality_flags else None
    row.completeness_status = feat.completeness_status
    row.calculated_at = datetime.now(timezone.utc)
    db.flush()
    return row


class MarketEnrichmentService:
    def __init__(self, db: Session, provider=None):
        self.db = db
        self.provider = provider or get_market_data_provider()
        self.stats = FetchStats()
        self.adjustment_mode = settings.market_adjustment_mode

    def enrich(
        self,
        scope: str = "missing",
        dry_run: bool = False,
        fetch_from_provider: bool = True,
        overwrite_bars: bool = False,
        calculation_version: str | None = None,
    ) -> dict:
        calc_version = calculation_version or CALCULATION_VERSION
        self.stats = FetchStats()
        job = MarketEnrichmentJob(
            provider=getattr(self.provider, "provider_name", "NONE"),
            feed=getattr(self.provider, "feed_name", "none"),
            status="RUNNING",
        )
        if not dry_run:
            self.db.add(job)
            self.db.flush()

        trades = self._trades_for_scope(scope)
        job.trades_requested = len(trades)
        if not trades:
            job.status = "SUCCESS"
            job.completed_at = datetime.now(timezone.utc)
            if not dry_run:
                self.db.commit()
            return self._job_summary(job, dry_run)

        symbol_dates: dict[str, set[date]] = {}
        all_dates: set[date] = set()
        for t in trades:
            d = ny_date_from_utc(t.entry_time_utc)
            symbol_dates.setdefault(t.ticker.upper(), set()).add(d)
            all_dates.add(d)

        benchmark = settings.market_benchmark.upper()
        symbol_dates.setdefault(benchmark, set()).update(all_dates)
        job.symbols_requested = len(symbol_dates)

        if dry_run:
            return {
                "dry_run": True,
                "trades": len(trades),
                "symbols": len(symbol_dates),
                "provider": job.provider,
            }

        lookback = settings.market_lookback_calendar_days
        earliest = min(all_dates) - timedelta(days=lookback)
        latest = max(all_dates)
        now = utc_now()
        today_ny = ny_date_from_utc(now)
        session_complete = ny_regular_session_complete(now)
        split_meta = bool(getattr(self.provider, "supports_splits", False))

        inst_by_symbol_date: dict[tuple[str, date], InstrumentDayFeature] = {}

        for symbol, dates in symbol_dates.items():
            try:
                cached = self._load_with_gaps(
                    symbol, earliest, latest, fetch_from_provider, overwrite_bars
                )
                cached = self._extend_history_if_needed(
                    symbol, cached, dates, earliest, latest, fetch_from_provider, overwrite_bars
                )
                sessions = _sessions_from_bars(cached)
                date_index = {s.trading_date: i for i, s in enumerate(sessions)}

                for td in dates:
                    idx = date_index.get(td)
                    if idx is None:
                        job.missing_count += 1
                        continue
                    incomplete = td == today_ny and not session_complete
                    feat = compute_day_features(
                        sessions,
                        idx,
                        is_consolidated=self.provider.is_consolidated,
                        is_today_incomplete=incomplete,
                        split_metadata_available=split_meta,
                    )
                    row = _persist_day_feature(
                        self.db,
                        symbol,
                        td,
                        feat,
                        self.provider.provider_name,
                        self.provider.feed_name,
                        self.adjustment_mode,
                        calc_version,
                    )
                    inst_by_symbol_date[(symbol, td)] = row
                    job.features_calculated += 1
            except Exception as exc:
                logger.warning("Market enrichment failed for %s: %s", symbol, exc)
                job.error_count += 1
                job.error_message = str(exc)[:500]

        bench_features: dict[date, InstrumentDayFeature] = {
            td: row for (sym, td), row in inst_by_symbol_date.items() if sym == benchmark
        }

        for t in trades:
            td = ny_date_from_utc(t.entry_time_utc)
            inst = inst_by_symbol_date.get((t.ticker.upper(), td))
            if inst is None:
                inst = (
                    self.db.query(InstrumentDayFeature)
                    .filter(
                        InstrumentDayFeature.symbol == t.ticker.upper(),
                        InstrumentDayFeature.trading_date == td.isoformat(),
                        InstrumentDayFeature.provider == self.provider.provider_name,
                        InstrumentDayFeature.feed == self.provider.feed_name,
                        InstrumentDayFeature.adjustment_mode == self.adjustment_mode,
                        InstrumentDayFeature.calculation_version == calc_version,
                    )
                    .first()
                )
            bench = bench_features.get(td)
            self._link_trade(t, inst, benchmark, bench, job)

        job.bars_fetched = self.stats.bars_fetched
        job.cache_hits = self.stats.cache_hits
        job.completed_at = datetime.now(timezone.utc)
        job.status = "SUCCESS" if job.error_count == 0 else "PARTIAL"
        self.db.commit()
        return self._job_summary(job, dry_run=False)

    def recalculate(self) -> dict:
        """Recalculate features from cached bars only — never calls the provider."""
        return self.enrich(scope="all", fetch_from_provider=False, overwrite_bars=False)

    def refresh(self, scope: str = "all") -> dict:
        """Deliberate provider fetch; may overwrite cached bars for the same provenance."""
        return self.enrich(scope=scope, fetch_from_provider=True, overwrite_bars=True)

    def _load_with_gaps(
        self,
        symbol: str,
        earliest: date,
        latest: date,
        fetch_from_provider: bool,
        overwrite_bars: bool,
    ):
        cached = load_cached_bars(
            self.db,
            symbol,
            earliest,
            latest,
            self.provider.provider_name,
            self.provider.feed_name,
            self.adjustment_mode,
        )
        probed = load_probed_range(
            self.db,
            symbol,
            self.provider.provider_name,
            self.provider.feed_name,
            self.adjustment_mode,
        )
        gaps = missing_date_ranges(cached, earliest, latest, probed=probed)
        if (gaps and fetch_from_provider) or (overwrite_bars and fetch_from_provider):
            fetch_start, fetch_end = earliest, latest
            fetched = self.provider.get_daily_bars(
                [symbol],
                fetch_start,
                fetch_end,
                self.adjustment_mode,
                self.stats,
            )
            store_bars(self.db, fetched, overwrite=overwrite_bars)
            mark_probed(
                self.db,
                symbol,
                self.provider.provider_name,
                self.provider.feed_name,
                self.adjustment_mode,
                fetch_start,
                fetch_end,
            )
            cached = load_cached_bars(
                self.db,
                symbol,
                earliest,
                latest,
                self.provider.provider_name,
                self.provider.feed_name,
                self.adjustment_mode,
            )
        elif cached:
            self.stats.cache_hits += 1
        return cached

    def _extend_history_if_needed(
        self,
        symbol: str,
        cached,
        dates: set[date],
        earliest: date,
        latest: date,
        fetch_from_provider: bool,
        overwrite_bars: bool,
    ):
        if not fetch_from_provider:
            return cached
        sessions = _sessions_from_bars(cached)
        date_index = {s.trading_date: i for i, s in enumerate(sessions)}
        needs_more = False
        for td in dates:
            idx = date_index.get(td)
            if idx is None or idx < MIN_RVOL_PRIOR_SESSIONS:
                needs_more = True
                break
        if not needs_more:
            return cached
        extended_start = earliest - timedelta(days=EXTENDED_LOOKBACK_DAYS)
        probed = load_probed_range(
            self.db,
            symbol,
            self.provider.provider_name,
            self.provider.feed_name,
            self.adjustment_mode,
        )
        extra_gaps = missing_date_ranges(cached, extended_start, earliest - timedelta(days=1), probed=probed)
        if not extra_gaps:
            return cached
        fetched = self.provider.get_daily_bars(
            [symbol],
            extended_start,
            latest,
            self.adjustment_mode,
            self.stats,
        )
        store_bars(self.db, fetched, overwrite=overwrite_bars)
        mark_probed(
            self.db,
            symbol,
            self.provider.provider_name,
            self.provider.feed_name,
            self.adjustment_mode,
            extended_start,
            latest,
        )
        return load_cached_bars(
            self.db,
            symbol,
            extended_start,
            latest,
            self.provider.provider_name,
            self.provider.feed_name,
            self.adjustment_mode,
        )

    def _trades_for_scope(self, scope: str) -> list[Trade]:
        q = self.db.query(Trade).filter(Trade.status == "CLOSED")
        if scope == "missing":
            enriched_ids = {
                r[0]
                for r in self.db.query(TradeMarketFeature.trade_id)
                .filter(TradeMarketFeature.enrichment_status == "COMPLETE")
                .all()
            }
            if enriched_ids:
                q = q.filter(~Trade.id.in_(enriched_ids))
        return q.all()

    def _link_trade(
        self,
        trade: Trade,
        inst: InstrumentDayFeature | None,
        benchmark: str,
        bench: InstrumentDayFeature | None,
        job: MarketEnrichmentJob,
    ) -> None:
        row = self.db.query(TradeMarketFeature).filter(TradeMarketFeature.trade_id == trade.id).first()
        if not row:
            row = TradeMarketFeature(
                trade_id=trade.id,
                calculation_version=CALCULATION_VERSION,
            )
            self.db.add(row)

        row.instrument_feature_id = inst.id if inst else None
        row.benchmark_feature_id = bench.id if bench else None
        row.benchmark_symbol = benchmark
        row.calculation_version = inst.calculation_version if inst else CALCULATION_VERSION

        if inst and inst.prior_close is not None and inst.atr14_prior:
            row.entry_vs_atr_pct = entry_vs_atr_pct(
                trade.avg_entry_price, inst.prior_close, inst.atr14_prior
            )
            row.entry_vs_sma20_pct = entry_vs_sma_pct(trade.avg_entry_price, inst.sma20_prior)
            row.entry_vs_sma50_pct = entry_vs_sma_pct(trade.avg_entry_price, inst.sma50_prior)
            row.enrichment_status = "COMPLETE" if inst.completeness_status == "COMPLETE" else "PARTIAL"
            row.missing_reason = None if inst.completeness_status == "COMPLETE" else inst.quality_status
            job.success_count += 1
        elif inst:
            row.entry_vs_atr_pct = (
                entry_vs_atr_pct(trade.avg_entry_price, inst.prior_close, inst.atr14_prior)
                if inst.prior_close is not None
                else None
            )
            row.entry_vs_sma20_pct = entry_vs_sma_pct(trade.avg_entry_price, inst.sma20_prior)
            row.entry_vs_sma50_pct = entry_vs_sma_pct(trade.avg_entry_price, inst.sma50_prior)
            row.enrichment_status = "PARTIAL"
            row.missing_reason = inst.quality_status
            job.success_count += 1
        else:
            row.enrichment_status = "FAILED"
            row.missing_reason = "MISSING_BAR"
            job.missing_count += 1

        row.calculated_at = datetime.now(timezone.utc)

    def _job_summary(self, job: MarketEnrichmentJob, dry_run: bool) -> dict:
        return {
            "job_id": job.id,
            "status": job.status,
            "dry_run": dry_run,
            "trades_requested": job.trades_requested,
            "symbols_requested": job.symbols_requested,
            "bars_fetched": job.bars_fetched,
            "cache_hits": job.cache_hits,
            "features_calculated": job.features_calculated,
            "success_count": job.success_count,
            "missing_count": job.missing_count,
            "error_count": job.error_count,
            "provider_requests": self.stats.provider_requests,
            "provider": job.provider,
            "feed": job.feed,
        }


def get_coverage(db: Session) -> dict:
    total = db.query(Trade).filter(Trade.status == "CLOSED").count()
    enriched = (
        db.query(TradeMarketFeature)
        .filter(TradeMarketFeature.enrichment_status.in_(["COMPLETE", "PARTIAL"]))
        .count()
    )
    inst = db.query(InstrumentDayFeature).count()
    return {
        "total_trades": total,
        "instrument_enriched": enriched,
        "market_enriched": enriched,
        "instrument_features": inst,
        "coverage_pct": round(enriched / total * 100, 1) if total else 0.0,
    }
