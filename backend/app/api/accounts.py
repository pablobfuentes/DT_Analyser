from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.models.account import Account
from app.db.session import get_db
from app.schemas import AccountCreate, AccountResponse, AccountUpdate
from app.services.data_reset import clear_all_trading_data

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def utcnow():
    return datetime.now(timezone.utc)


@router.get("", response_model=list[AccountResponse])
def list_accounts(db: Session = Depends(get_db)):
    return db.query(Account).order_by(Account.id).all()


@router.post("", response_model=AccountResponse, status_code=201)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)):
    existing = db.query(Account).filter(Account.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Account name already exists")
    if payload.starting_equity is not None and payload.starting_equity < 0:
        raise HTTPException(status_code=422, detail="starting_equity cannot be negative")
    account = Account(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(account_id: int, payload: AccountUpdate, db: Session = Depends(get_db)):
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    data = payload.model_dump(exclude_unset=True)
    if "starting_equity" in data and data["starting_equity"] is not None and data["starting_equity"] < 0:
        raise HTTPException(status_code=422, detail="starting_equity cannot be negative")
    if "name" in data and data["name"]:
        existing = db.query(Account).filter(Account.name == data["name"], Account.id != account_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="Account name already exists")
    for key, value in data.items():
        setattr(account, key, value)
    account.updated_at = utcnow()
    db.commit()
    db.refresh(account)
    return account


@router.post("/clear-data")
def clear_data(db: Session = Depends(get_db)):
    """Remove all trades, executions, and import history. Accounts are kept."""
    counts = clear_all_trading_data(db)
    return {"status": "ok", "deleted": counts}
