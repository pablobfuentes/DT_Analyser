"""Normalize values from TradingView and broker CSV exports."""


def normalize_ticker(symbol: str) -> str:
    """Strip exchange prefix (e.g. NASDAQ:PPCB -> PPCB)."""
    s = str(symbol).strip().upper()
    if ":" in s:
        return s.rsplit(":", 1)[-1]
    return s
