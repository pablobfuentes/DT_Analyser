"""User-adjustable preferences. Secrets stay in environment variables."""

from __future__ import annotations

import json
from copy import deepcopy

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.automation import AppPreference, utcnow

SECRET_KEYS = frozenset({
    "alpaca_api_key_id",
    "alpaca_api_secret_key",
    "LTA_ALPACA_API_KEY_ID",
    "LTA_ALPACA_API_SECRET_KEY",
})

DEFAULTS: dict = {
    "auto_process_inbox": True,
    "eod_finalize_enabled": True,
    "eod_finalize_time": "20:15",
    "automatic_backup": True,
    "backup_retain_daily": 30,
    "backup_retain_weekly": 12,
    "notifications": "important",
    "expected_inputs": {
        "ORDER_HISTORY": "REQUIRED",
        "PINE_LOG": "RECOMMENDED",
        "ACTIVITY_LOG": "OPTIONAL",
        "AUTO_STRATEGY_TESTER": "OPTIONAL",
    },
    "inbox_path_override": None,
    "archive_path_override": None,
    "backup_path_override": None,
}

DAILY_PROMPTS = [
    "What worked today?",
    "What hurt performance?",
    "Did I follow my process?",
    "What should I repeat tomorrow?",
    "What should I avoid tomorrow?",
    "Anything unusual about market conditions?",
]

WEEKLY_PROMPTS = [
    "What improved?",
    "What repeated mistake appeared?",
    "Which setups felt easiest to execute?",
    "Which trades deserve deeper Research Lab review?",
    "What should I focus on next week?",
]

TRADE_PROMPTS = [
    "Trade Thesis",
    "Why I Entered",
    "Why I Exited",
    "What Went Well",
    "What I Would Change",
    "Additional Notes",
]


def _row_map(db: Session) -> dict[str, AppPreference]:
    return {r.key: r for r in db.query(AppPreference).all()}


def get_all(db: Session) -> dict:
    out = deepcopy(DEFAULTS)
    out["auto_process_inbox"] = settings.auto_process_inbox
    out["eod_finalize_enabled"] = settings.eod_finalize_enabled
    out["eod_finalize_time"] = f"{settings.eod_finalize_hour:02d}:{settings.eod_finalize_minute:02d}"
    out["automatic_backup"] = settings.automatic_backup
    out["backup_retain_daily"] = settings.backup_retain_daily
    out["backup_retain_weekly"] = settings.backup_retain_weekly
    for row in db.query(AppPreference).all():
        if row.key in SECRET_KEYS:
            continue
        try:
            out[row.key] = json.loads(row.value_json)
        except json.JSONDecodeError:
            out[row.key] = row.value_json
    return out


def get_pref(db: Session, key: str, default=None):
    row = db.query(AppPreference).filter(AppPreference.key == key).first()
    if row is None:
        return DEFAULTS.get(key, default)
    try:
        return json.loads(row.value_json)
    except json.JSONDecodeError:
        return row.value_json


def set_pref(db: Session, key: str, value) -> None:
    if key in SECRET_KEYS:
        raise ValueError("Secrets cannot be stored in preferences")
    rows = _row_map(db)
    payload = json.dumps(value)
    if key in rows:
        rows[key].value_json = payload
        rows[key].updated_at = utcnow()
    else:
        db.add(AppPreference(key=key, value_json=payload))
    db.flush()


def update_prefs(db: Session, patch: dict) -> dict:
    for key, value in patch.items():
        if key in SECRET_KEYS:
            continue
        set_pref(db, key, value)
    db.commit()
    return get_all(db)


def expected_inputs(db: Session) -> dict[str, str]:
    raw = get_pref(db, "expected_inputs") or DEFAULTS["expected_inputs"]
    return {str(k): str(v).upper() for k, v in raw.items()}
