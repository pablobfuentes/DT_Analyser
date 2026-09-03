"""Alpaca historical market data provider."""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

from app.market_data.base import MarketDataProvider
from app.market_data.models import DailyBar, FetchStats, IntradayBar, SplitEvent

logger = logging.getLogger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets/v2/stocks/bars"
MAX_ATTEMPTS = 5
PERMANENT_CLIENT_ERRORS = frozenset({400, 401, 403, 404, 422})


def _retry_sleep(seconds: float) -> None:
    """Isolated so tests can patch without waiting real seconds."""
    time.sleep(seconds)


def _redact(text: str) -> str:
    lowered = text.lower()
    if "apca-api" in lowered or "secret" in lowered or "authorization" in lowered:
        return "[redacted]"
    return text


class AlpacaMarketDataProvider(MarketDataProvider):
    def __init__(self, api_key: str, api_secret: str, feed: str = "iex"):
        self._api_key = api_key
        self._api_secret = api_secret
        self.feed_name = feed.lower()
        self.provider_name = "ALPACA"
        self.is_consolidated = self.feed_name == "sip"
        self.supports_splits = False
        self.supports_batch_symbols = True
        self.supports_intraday = True

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

    def _get_json(self, params: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.get(ALPACA_DATA_URL, headers=self._headers(), params=params)
                if resp.status_code == 429:
                    _retry_sleep(2 ** attempt)
                    continue
                if resp.status_code in PERMANENT_CLIENT_ERRORS:
                    logger.warning(
                        "Alpaca request rejected status=%s (credentials redacted)",
                        resp.status_code,
                    )
                    resp.raise_for_status()
                if 400 <= resp.status_code < 500:
                    logger.warning("Alpaca client error status=%s", resp.status_code)
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else None
                if status in PERMANENT_CLIENT_ERRORS or (status and 400 <= status < 500 and status != 429):
                    raise
                last_error = e
                logger.warning("Alpaca fetch attempt %s failed status=%s", attempt + 1, status)
            except httpx.HTTPError as e:
                last_error = e
                logger.warning("Alpaca fetch attempt %s failed: %s", attempt + 1, _redact(str(e)))
            if attempt < MAX_ATTEMPTS - 1:
                _retry_sleep(2 ** attempt)
        if last_error:
            raise last_error
        return {}

    def get_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adjustment_mode: str = "raw",
        stats: FetchStats | None = None,
    ) -> list[DailyBar]:
        if not symbols:
            return []
        if stats:
            stats.provider_requests += 1

        params = {
            "symbols": ",".join(s.upper() for s in symbols),
            "timeframe": "1Day",
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "adjustment": adjustment_mode if adjustment_mode in ("raw", "split", "dividend", "all") else "raw",
            "feed": self.feed_name,
            "limit": 10000,
        }

        data = self._get_json(params)
        bars: list[DailyBar] = []
        now = datetime.now(timezone.utc)
        for sym, sym_bars in (data.get("bars") or {}).items():
            for row in sym_bars:
                ts = row.get("t", "")[:10]
                bars.append(
                    DailyBar(
                        symbol=sym.upper(),
                        trading_date=date.fromisoformat(ts),
                        open=Decimal(str(row["o"])),
                        high=Decimal(str(row["h"])),
                        low=Decimal(str(row["l"])),
                        close=Decimal(str(row["c"])),
                        volume=int(row["v"]),
                        vwap=Decimal(str(row["vw"])) if row.get("vw") is not None else None,
                        trade_count=int(row["n"]) if row.get("n") is not None else None,
                        provider=self.provider_name,
                        feed=self.feed_name,
                        adjustment_mode=adjustment_mode,
                        is_consolidated=self.is_consolidated,
                        fetched_at=now,
                        raw_payload_json=json.dumps(row),
                    )
                )
        if stats:
            stats.bars_fetched += len(bars)
        return bars

    def get_intraday_bars(
        self,
        symbols: list[str],
        start_utc: datetime,
        end_utc: datetime,
        timeframe: str = "1Min",
        adjustment_mode: str = "raw",
        stats: FetchStats | None = None,
    ) -> list[IntradayBar]:
        if not symbols:
            return []
        if stats:
            stats.provider_requests += 1

        params = {
            "symbols": ",".join(s.upper() for s in symbols),
            "timeframe": timeframe,
            "start": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end": end_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "adjustment": adjustment_mode if adjustment_mode in ("raw", "split", "dividend", "all") else "raw",
            "feed": self.feed_name,
            "limit": 10000,
        }

        data = self._get_json(params)
        bars: list[IntradayBar] = []
        now = datetime.now(timezone.utc)
        for sym, sym_bars in (data.get("bars") or {}).items():
            for row in sym_bars:
                ts_raw = row.get("t", "")
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                bars.append(
                    IntradayBar(
                        symbol=sym.upper(),
                        bar_time_utc=ts,
                        timeframe=timeframe,
                        open=Decimal(str(row["o"])),
                        high=Decimal(str(row["h"])),
                        low=Decimal(str(row["l"])),
                        close=Decimal(str(row["c"])),
                        volume=int(row["v"]),
                        vwap=Decimal(str(row["vw"])) if row.get("vw") is not None else None,
                        trade_count=int(row["n"]) if row.get("n") is not None else None,
                        provider=self.provider_name,
                        feed=self.feed_name,
                        adjustment_mode=adjustment_mode,
                        is_consolidated=self.is_consolidated,
                        fetched_at=now,
                    )
                )
        if stats:
            stats.bars_fetched += len(bars)
        return bars

    def get_splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        """Alpaca split metadata is not wired; rolling price features are unverified across splits."""
        return []
