from collections.abc import Generator
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)


def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def _make_engine():
    eng = create_engine(
        settings.sync_database_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    event.listen(eng, "connect", _set_sqlite_pragma)
    return eng


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def dispose_engine() -> None:
    """Drop pooled connections so the SQLite file can be replaced."""
    engine.dispose()


def recreate_engine() -> None:
    """Dispose the live engine and bind SessionLocal to a new pool.

    Importers of SessionLocal keep working via sessionmaker.configure.
    Callers that imported `engine` at module load must re-import from this module.
    """
    global engine
    try:
        engine.dispose()
    except Exception:
        logger.exception("Engine dispose during recreate failed")
    engine = _make_engine()
    SessionLocal.configure(bind=engine)
    logger.info("SQLAlchemy engine recreated")
