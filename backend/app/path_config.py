"""Persistent path overrides.

Stored outside the SQLite data dir so the app can find the data root on startup.
File: `{platform_default_data_dir}/app_paths.json`
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_NAME = "app_paths.json"
KNOWN_KEYS = (
    "data_dir",
    "inbox",
    "archive",
    "quarantine",
    "screenshots",
    "backups",
    "logs",
    "paste",
    "uploads",
)


def platform_default_data_dir() -> Path:
    import os
    import sys

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "LocalTraderAnalyzer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LocalTraderAnalyzer"
    return Path.home() / ".local" / "share" / "local-trader-analyzer"


def path_config_file() -> Path:
    return platform_default_data_dir() / CONFIG_NAME


def load_path_config() -> dict[str, str]:
    path = path_config_file()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read path config %s: %s", path, exc)
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key in KNOWN_KEYS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    return out


def save_path_config(patch: dict[str, str | None]) -> dict[str, str]:
    """Merge patch into config. Empty / null values clear an override."""
    current = load_path_config()
    for key in KNOWN_KEYS:
        if key not in patch:
            continue
        val = patch[key]
        if val is None or (isinstance(val, str) and not val.strip()):
            current.pop(key, None)
        else:
            current[key] = str(val).strip()
    dest = path_config_file()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return current
