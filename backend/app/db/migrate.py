"""SQLite schema migrations."""

import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)


def _bind(engine=None):
    if engine is not None:
        return engine
    from app.db import session as db_session

    return db_session.engine


def run_migrations(engine=None) -> None:
    eng = _bind(engine)
    with eng.connect() as conn:
        inspector = inspect(conn)
        if "accounts" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("accounts")}
            if "starting_equity" not in cols:
                conn.execute(text("ALTER TABLE accounts ADD COLUMN starting_equity NUMERIC(18, 6)"))
                conn.commit()
                logger.info("Added accounts.starting_equity column")
        _ensure_trade_execution_columns(conn)
        _ensure_import_error_columns(conn)
        _ensure_trade_risk_columns(conn)
        _ensure_trade_indexes(conn)
        _ensure_instrument_feature_provenance(conn)
        _backfill_trade_risk(conn)


def _ensure_trade_risk_columns(conn) -> None:
    inspector = inspect(conn)
    if "trades" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("trades")}
    additions = [
        ("initial_stop_price", "NUMERIC(18, 6)"),
        ("initial_risk_per_share", "NUMERIC(18, 6)"),
        ("initial_risk_amount", "NUMERIC(18, 6)"),
        ("r_multiple", "NUMERIC(18, 8)"),
        ("risk_source", "VARCHAR(16)"),
        ("risk_notes", "TEXT"),
        ("risk_updated_at", "DATETIME"),
    ]
    added = False
    for name, col_type in additions:
        if name not in cols:
            conn.execute(text(f"ALTER TABLE trades ADD COLUMN {name} {col_type}"))
            added = True
    if added:
        conn.commit()
        logger.info("Added trade risk columns")


def _ensure_trade_execution_columns(conn) -> None:
    inspector = inspect(conn)
    if "trade_executions" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("trade_executions")}
    if "allocated_quantity" not in cols:
        conn.execute(
            text("ALTER TABLE trade_executions ADD COLUMN allocated_quantity NUMERIC(18, 6)")
        )
        conn.execute(
            text(
                """
                UPDATE trade_executions
                SET allocated_quantity = (
                    SELECT quantity FROM executions WHERE executions.id = trade_executions.execution_id
                )
                WHERE allocated_quantity IS NULL
                """
            )
        )
        conn.commit()
        logger.info("Added trade_executions.allocated_quantity column")


def _ensure_import_error_columns(conn) -> None:
    inspector = inspect(conn)
    if "import_errors" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("import_errors")}
    if "resolved_at" not in cols:
        conn.execute(text("ALTER TABLE import_errors ADD COLUMN resolved_at DATETIME"))
        conn.commit()
        logger.info("Added import_errors.resolved_at column")


def _ensure_trade_indexes(conn) -> None:
    """Create dashboard indexes if missing (SQLite IF NOT EXISTS)."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_trades_exit_time ON trades (exit_time_utc)",
        "CREATE INDEX IF NOT EXISTS ix_trades_account_id ON trades (account_id)",
        "CREATE INDEX IF NOT EXISTS ix_trades_status ON trades (status)",
        "CREATE INDEX IF NOT EXISTS ix_trades_source_type ON trades (source_type)",
        "CREATE INDEX IF NOT EXISTS ix_trades_account_status ON trades (account_id, status)",
    ]
    for stmt in indexes:
        conn.execute(text(stmt))
    conn.commit()


def _ensure_instrument_feature_provenance(conn) -> None:
    """Add provider/feed/adjustment_mode to derived-feature uniqueness without dropping user data."""
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if "instrument_day_features" not in tables:
        return

    cols = {c["name"] for c in inspector.get_columns("instrument_day_features")}
    added = False
    if "adjustment_mode" not in cols:
        conn.execute(text("ALTER TABLE instrument_day_features ADD COLUMN adjustment_mode VARCHAR(16) DEFAULT 'raw'"))
        added = True
    if "quality_flags" not in cols:
        conn.execute(text("ALTER TABLE instrument_day_features ADD COLUMN quality_flags TEXT"))
        added = True
    if added:
        conn.execute(
            text("UPDATE instrument_day_features SET adjustment_mode = 'raw' WHERE adjustment_mode IS NULL")
        )

    conn.execute(text("DROP INDEX IF EXISTS uq_instrument_day"))
    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_instrument_day_prov
            ON instrument_day_features (
                symbol, trading_date, provider, feed, adjustment_mode, calculation_version
            )
            """
        )
    )
    conn.commit()
    if added:
        logger.info("Migrated instrument_day_features provenance unique key")


def pending_schema_mutations(engine=None) -> list[str]:
    """ALTER / missing-table mutations that would run. Indexes and backfills excluded.

    Used to take one PRE_MIGRATION backup when user data exists. Not every startup.
    """
    from app.db.base import Base
    from app.db import models  # noqa: F401

    eng = _bind(engine)
    pending: list[str] = []
    with eng.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        if "accounts" in tables:
            cols = {c["name"] for c in inspector.get_columns("accounts")}
            if "starting_equity" not in cols:
                pending.append("accounts.starting_equity")
        if "trades" in tables:
            cols = {c["name"] for c in inspector.get_columns("trades")}
            for name in (
                "initial_stop_price",
                "initial_risk_per_share",
                "initial_risk_amount",
                "r_multiple",
                "risk_source",
                "risk_notes",
                "risk_updated_at",
            ):
                if name not in cols:
                    pending.append(f"trades.{name}")
        if "trade_executions" in tables:
            cols = {c["name"] for c in inspector.get_columns("trade_executions")}
            if "allocated_quantity" not in cols:
                pending.append("trade_executions.allocated_quantity")
        if "import_errors" in tables:
            cols = {c["name"] for c in inspector.get_columns("import_errors")}
            if "resolved_at" not in cols:
                pending.append("import_errors.resolved_at")
        if "instrument_day_features" in tables:
            cols = {c["name"] for c in inspector.get_columns("instrument_day_features")}
            if "adjustment_mode" not in cols:
                pending.append("instrument_day_features.adjustment_mode")
            if "quality_flags" not in cols:
                pending.append("instrument_day_features.quality_flags")
        expected = set(Base.metadata.tables)
        pending.extend(f"table:{name}" for name in sorted(expected - tables))
    return pending


def _backfill_trade_risk(conn) -> None:
    """Copy pre-Step-7 trade cache into trade_risk without labeling unknown as PINE."""
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if "trades" not in tables or "trade_risk" not in tables:
        return
    conn.execute(
        text(
            """
            INSERT INTO trade_risk (
                trade_id, initial_stop_price, actual_risk_per_share, actual_initial_risk_amount,
                r_multiple, risk_source, stop_source, risk_notes, risk_quality_status,
                calculation_version, manual_override, created_at, updated_at
            )
            SELECT
                t.id, t.initial_stop_price, t.initial_risk_per_share, t.initial_risk_amount,
                t.r_multiple,
                CASE t.risk_source WHEN 'PINE' THEN 'PINE_SIGNAL' ELSE t.risk_source END,
                CASE t.risk_source WHEN 'PINE' THEN 'PINE_SIGNAL' WHEN 'MANUAL' THEN 'MANUAL' ELSE t.risk_source END,
                t.risk_notes,
                CASE WHEN t.r_multiple IS NOT NULL THEN 'OK' ELSE NULL END,
                '1',
                CASE WHEN t.risk_source = 'MANUAL' THEN 1 ELSE 0 END,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM trades t
            WHERE (t.initial_stop_price IS NOT NULL OR t.initial_risk_amount IS NOT NULL)
              AND NOT EXISTS (SELECT 1 FROM trade_risk r WHERE r.trade_id = t.id)
            """
        )
    )
    conn.commit()


def pending_schema_mutations_at_path(db_path) -> list[str]:
    """Inspect a SQLite file with a throwaway engine (not the live pool)."""
    from pathlib import Path

    from sqlalchemy import create_engine

    path = Path(db_path)
    if not path.exists():
        return []
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    try:
        return pending_schema_mutations(eng)
    finally:
        eng.dispose()


def meaningful_user_data_count(db_path) -> int:
    """Row count of user-owned tables. Used to skip PRE_MIGRATION on empty DBs."""
    import sqlite3
    from pathlib import Path

    path = Path(db_path)
    if not path.exists():
        return 0
    conn = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        total = 0
        for name in ("trades", "executions", "signals", "journal_entries", "journal_attachments"):
            if name in tables:
                total += int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        return total
    finally:
        conn.close()


def pre_migration_signature(pending: list[str]) -> str:
    import hashlib

    return hashlib.sha256(",".join(pending).encode("utf-8")).hexdigest()[:16]

