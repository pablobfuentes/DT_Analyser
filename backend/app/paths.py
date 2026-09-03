"""Resolve the application data directory and well-known subfolders.

Production paths come from LTA_DATA_DIR. Existing ./data installs are preserved.
User overrides live in app_paths.json (see path_config).
"""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.path_config import load_path_config, platform_default_data_dir

SUBDIRS = ("inbox", "archive", "quarantine", "screenshots", "backups", "logs", "paste", "uploads")


def resolve_data_dir() -> Path:
    if settings.data_dir is not None:
        return Path(settings.data_dir).expanduser().resolve()
    cfg = load_path_config()
    if cfg.get("data_dir"):
        return Path(cfg["data_dir"]).expanduser().resolve()
    cwd_data = Path("./data")
    if cwd_data.exists():
        return cwd_data.resolve()
    return platform_default_data_dir().resolve()


def data_layout(root: Path | None = None) -> dict[str, Path]:
    base = root or resolve_data_dir()
    cfg = load_path_config()
    layout = {"root": base}
    for name in SUBDIRS:
        override = cfg.get(name)
        if override:
            layout[name] = Path(override).expanduser().resolve()
        else:
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
