"""User preferences. Secrets remain environment-only."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.path_config import load_path_config, path_config_file, save_path_config
from app.paths import data_layout, ensure_data_layout, resolve_data_dir, sqlite_file_path
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
    paths: dict[str, str | None] | None = Field(
        default=None,
        description="Optional path overrides: data_dir, inbox, archive, screenshots, backups, …",
    )


def _paths_payload() -> dict:
    layout = data_layout()
    cfg = load_path_config()
    db_path = sqlite_file_path()
    return {
        "data_dir": str(resolve_data_dir()),
        "database": str(db_path or settings.database_url),
        "inbox": str(layout["inbox"]),
        "archive": str(layout["archive"]),
        "quarantine": str(layout["quarantine"]),
        "screenshots": str(layout["screenshots"]),
        "backups": str(layout["backups"]),
        "logs": str(layout["logs"]),
        "overrides": cfg,
        "config_file": str(path_config_file()),
    }


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    prefs = get_all(db)
    return {
        "preferences": prefs,
        "paths": _paths_payload(),
        "secrets_note": "API keys stay in environment variables and are never shown here.",
        "daily_prompts": __import__("app.services.preferences", fromlist=["DAILY_PROMPTS"]).DAILY_PROMPTS,
        "weekly_prompts": __import__("app.services.preferences", fromlist=["WEEKLY_PROMPTS"]).WEEKLY_PROMPTS,
    }


@router.patch("")
def patch_settings(body: SettingsPatch, db: Session = Depends(get_db)):
    patch = {k: v for k, v in body.model_dump().items() if v is not None and k != "paths"}
    if any(k in SECRET_KEYS for k in patch):
        raise HTTPException(400, "Secrets cannot be stored in preferences")
    prefs = update_prefs(db, patch) if patch else get_all(db)

    restart_required = False
    note = None
    if body.paths is not None:
        incoming = body.paths
        data_dir_raw = incoming.get("data_dir")
        if data_dir_raw is not None and str(data_dir_raw).strip():
            data_root = Path(str(data_dir_raw).strip()).expanduser().resolve()
        else:
            data_root = resolve_data_dir()

        cleaned: dict[str, str | None] = {}
        if "data_dir" in incoming:
            if data_dir_raw is None or not str(data_dir_raw).strip():
                cleaned["data_dir"] = None
            else:
                try:
                    data_root.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise HTTPException(400, f"Cannot create path for data_dir: {exc}") from exc
                cleaned["data_dir"] = str(data_root)

        for key in (
            "inbox",
            "archive",
            "quarantine",
            "screenshots",
            "backups",
            "logs",
            "paste",
            "uploads",
        ):
            if key not in incoming:
                continue
            val = incoming[key]
            if val is None or not str(val).strip():
                cleaned[key] = None
                continue
            p = Path(str(val).strip()).expanduser().resolve()
            default = (data_root / key).resolve()
            if p == default:
                cleaned[key] = None
                continue
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise HTTPException(400, f"Cannot create path for {key}: {exc}") from exc
            cleaned[key] = str(p)

        old_data = str(resolve_data_dir())
        save_path_config(cleaned)
        new_data = str(resolve_data_dir())
        ensure_data_layout()
        if cleaned.get("data_dir") and new_data != old_data:
            restart_required = True
            note = (
                "Trading data directory changed. Restart the app so the database and "
                "automation lock use the new location. Existing files are not moved automatically."
            )

    return {
        "preferences": prefs,
        "paths": _paths_payload(),
        "restart_required": restart_required,
        "note": note,
    }
