"""User preferences. Secrets remain environment-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.paths import data_layout, resolve_data_dir, sqlite_file_path
from app.services.preferences import SECRET_KEYS, get_all, update_prefs

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsPatch(BaseModel):
    auto_process_inbox: bool | None = None
    eod_finalize_enabled: bool | None = None
    eod_finalize_time: str | None = None
    automatic_backup: bool | None = None
    backup_retain_daily: int | None = None
    backup_retain_weekly: int | None = None
    notifications: str | None = None
    expected_inputs: dict[str, str] | None = None


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    layout = data_layout()
    prefs = get_all(db)
    return {
        "preferences": prefs,
        "paths": {
            "data_dir": str(resolve_data_dir()),
            "inbox": str(layout["inbox"]),
            "archive": str(layout["archive"]),
            "quarantine": str(layout["quarantine"]),
            "screenshots": str(layout["screenshots"]),
            "backups": str(layout["backups"]),
            "logs": str(layout["logs"]),
            "database": str(sqlite_file_path() or settings.database_url),
        },
        "secrets_note": "API keys stay in environment variables and are never shown here.",
        "daily_prompts": __import__("app.services.preferences", fromlist=["DAILY_PROMPTS"]).DAILY_PROMPTS,
        "weekly_prompts": __import__("app.services.preferences", fromlist=["WEEKLY_PROMPTS"]).WEEKLY_PROMPTS,
    }


@router.patch("")
def patch_settings(body: SettingsPatch, db: Session = Depends(get_db)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if any(k in SECRET_KEYS for k in patch):
        raise HTTPException(400, "Secrets cannot be stored in preferences")
    return {"preferences": update_prefs(db, patch)}
