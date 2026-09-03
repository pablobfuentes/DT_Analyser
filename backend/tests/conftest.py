import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import account as _account  # noqa: F401
from app.db.models import market_data as _market_data  # noqa: F401
from app.db.models import risk as _risk  # noqa: F401
from app.db.models import research as _research  # noqa: F401
from app.db.models import signal as _signal  # noqa: F401
from app.db.models import automation as _automation  # noqa: F401
from app.db.models import journal as _journal  # noqa: F401
from app.db.models import reviews as _reviews  # noqa: F401
from app.db.models.account import Account

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    account = Account(name="Test Manual", source="TRADINGVIEW_MANUAL", is_simulated=False)
    session.add(account)
    session.commit()
    yield session
    session.close()


@pytest.fixture
def manual_account(db_session):
    return db_session.query(Account).first()


@pytest.fixture
def strategy_account(db_session):
    acct = Account(name="Test Strategy", source="TRADINGVIEW_AUTO", is_simulated=True)
    db_session.add(acct)
    db_session.commit()
    return acct


def fixture_path(name: str) -> Path:
    return FIXTURES / name
