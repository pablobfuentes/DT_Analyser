"""Resolve the application data directory and well-known subfolders.

Production paths come from LTA_DATA_DIR. Existing ./data installs are preserved.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from app.config import settings

SUBDIRS = ("inbox", "archive", "quarantine", "screenshots", "backups", "logs", "paste", "uploads")


def platform_default_data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "LocalTraderAnalyzer"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LocalTraderAnalyzer"
    return Path.home() / ".local" / "share" / "local-trader-analyzer"


def resolve_data_dir() -> Path:
    if settings.data_dir is not None:
        return Path(settings.data_dir).expanduser().resolve()
    cwd_data = Path("./data")
    if cwd_data.exists():
        return cwd_data.resolve()
    return platform_default_data_dir().resolve()


def data_layout(root: Path | None = None) -> dict[str, Path]:
    base = root or resolve_data_dir()
    layout = {"root": base}
    for name in SUBDIRS:
        layout[name] = base / name
    return layout


def ensure_data_layout(root: Path | None = None) -> dict[str, Path]:
    layout = data_layout(root)
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    return layout


def safe_join(root: Path, *parts: str) -> Path:
    """Join under root; reject traversal and absolute fragments."""
    root_r = root.resolve()
    cleaned: list[str] = []
    for part in parts:
        raw = str(part).replace("\\", "/").strip()
        if not raw or raw.startswith("/") or (len(raw) >= 2 and raw[1] == ":"):
            raise ValueError("Unsafe path fragment")
        name = Path(raw).name
        if name in ("", ".", "..") or "\x00" in raw:
            raise ValueError("Unsafe path fragment")
        cleaned.append(name)
    dest = (root_r.joinpath(*cleaned)).resolve()
    dest.relative_to(root_r)
    return dest


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def sqlite_file_path(database_url: str | None = None) -> Path | None:
    url = database_url or settings.database_url
    if url.startswith("sqlite:///"):
        raw = url[len("sqlite:///") :]
        if raw == ":memory:" or raw.startswith("file:"):
            return None
        return Path(raw)
    return None
