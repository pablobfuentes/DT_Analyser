"""Pine SIGNALLOG must not change trading logic vs CURRENT Copilot."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "pine" / "Momentum_Pullback_Copilot_CURRENT.pine"
SIGNALLOG = ROOT / "pine" / "Momentum_Pullback_Copilot_SIGNALLOG.pine"

ANALYZER_LHS = {
    "activeSignalId",
    "activeSignalArmedBarTime",
    "loggedArmedThisOpportunity",
    "loggedEntryThisOpportunity",
    "loggedExitThisOpportunity",
}

ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:=")


def _trading_assignments(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        if "f_analyzer_" in line or "enableAnalyzerSignalLogs" in line:
            continue
        if "PINE_SIGNAL_EVENT" in line or line.startswith("ANALYZER_"):
            continue
        m = ASSIGN_RE.match(line)
        if not m:
            continue
        if m.group(1) in ANALYZER_LHS:
            continue
        out.append(line)
    return out


def test_signallog_observer_only_vs_current():
    current = CURRENT.read_text(encoding="utf-8")
    slog = SIGNALLOG.read_text(encoding="utf-8")
    assert "PINE_SIGNAL_EVENT" in slog
    assert "f_analyzer_signal_id" in slog
    assert "barstate.isrealtime" in slog
    for event in ("ARMED", "ENTRY", "EXIT"):
        assert event in slog

    cur_assign = _trading_assignments(current)
    slog_assign = _trading_assignments(slog)
    assert cur_assign == slog_assign, (
        "SIGNALLOG trading-state assignments differ from CURRENT Copilot. "
        f"current={len(cur_assign)} signallog={len(slog_assign)}"
    )


def test_signal_id_uses_armed_bar_not_future_entry():
    slog = SIGNALLOG.read_text(encoding="utf-8")
    assert "f_analyzer_signal_id(time)" in slog
    assert "ENTRY_BAR_UNIX_MS" not in slog
    # ID is minted at ARMED using current bar time; later ENTRY/EXIT reuse activeSignalId.
    assert "activeSignalId := f_analyzer_signal_id(time)" in slog
    assert "loggedArmedThisOpportunity := true" in slog
    assert "loggedEntryThisOpportunity := true" in slog
    assert "loggedExitThisOpportunity := true" in slog
