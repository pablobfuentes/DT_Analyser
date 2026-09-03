"""Clear all imported trading data while keeping accounts."""

from sqlalchemy.orm import Session

from app.db.models.execution import Execution
from app.db.models.import_batch import ImportBatch
from app.db.models.import_error import ImportError
from app.db.models.risk import RiskAuditLog, TradeRisk
from app.db.models.signal import (
    PineImportBatch,
    PineImportError,
    Signal,
    SignalEvent,
    SignalEventConflict,
    TradeSignalLink,
)
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.db.models.journal import JournalAttachment, JournalEntry, JournalEntryTag
from app.db.models.automation import AutomationFileEvent, AutomationRunStep


def clear_all_trading_data(db: Session) -> dict:
    """Delete trades, executions, imports, signals. Accounts are preserved."""
    db.query(JournalAttachment).delete(synchronize_session=False)
    db.query(JournalEntryTag).delete(synchronize_session=False)
    db.query(JournalEntry).delete(synchronize_session=False)
    db.query(AutomationRunStep).delete(synchronize_session=False)
    db.query(AutomationFileEvent).delete(synchronize_session=False)
    sig_links = db.query(TradeSignalLink).delete(synchronize_session=False)
    conflicts = db.query(SignalEventConflict).delete(synchronize_session=False)
    events = db.query(SignalEvent).delete(synchronize_session=False)
    pine_errors = db.query(PineImportError).delete(synchronize_session=False)
    signals = db.query(Signal).delete(synchronize_session=False)
    pine_batches = db.query(PineImportBatch).delete(synchronize_session=False)
    audit = db.query(RiskAuditLog).delete(synchronize_session=False)
    risks = db.query(TradeRisk).delete(synchronize_session=False)
    trade_exec = db.query(TradeExecution).delete(synchronize_session=False)
    trades = db.query(Trade).delete(synchronize_session=False)
    execs = db.query(Execution).delete(synchronize_session=False)
    errors = db.query(ImportError).delete(synchronize_session=False)
    batches = db.query(ImportBatch).delete(synchronize_session=False)
    db.commit()
    return {
        "trade_signal_links": sig_links,
        "signal_event_conflicts": conflicts,
        "signal_events": events,
        "signals": signals,
        "pine_import_errors": pine_errors,
        "pine_import_batches": pine_batches,
        "risk_audit_log": audit,
        "trade_risk": risks,
        "trade_executions": trade_exec,
        "trades": trades,
        "executions": execs,
        "import_errors": errors,
        "import_batches": batches,
    }
