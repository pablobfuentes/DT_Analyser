"""Serve the Vite production build from FastAPI (Windows .exe and local `python -m app.launcher`)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.paths import is_under

logger = logging.getLogger(__name__)


def bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def frontend_dist() -> Path | None:
    for candidate in (
        bundle_root() / "frontend" / "dist",
        Path(__file__).resolve().parents[2] / "frontend" / "dist",
    ):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def mount_frontend(app: FastAPI) -> None:
    dist = frontend_dist()
    if dist is None:
        logger.info("Frontend dist not found — API-only mode")
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        target = (dist / full_path).resolve()
        if full_path and target.is_file() and is_under(target, dist):
            return FileResponse(target)
        return FileResponse(dist / "index.html")

    logger.info("Serving UI from %s", dist)
