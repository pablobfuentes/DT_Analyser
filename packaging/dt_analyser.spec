# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

SPECDIR = Path(SPEC).resolve().parent
ROOT = SPECDIR.parent
FRONTEND_DIST = ROOT / "frontend" / "dist"
LAUNCHER = str(ROOT / "backend" / "app" / "launcher.py")

if not (FRONTEND_DIST / "index.html").is_file():
    raise SystemExit("frontend/dist missing. Build the frontend first (npm run build).")

datas = [(str(FRONTEND_DIST), "frontend/dist")]
datas += collect_data_files("tzdata")

binaries = []
hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "watchdog.observers.polling",
    "apscheduler.triggers.cron",
    "app.main",
    "app.launcher",
]

for pkg in ("polars", "numpy", "scipy", "pydantic", "fastapi", "starlette", "sqlalchemy"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

a = Analysis(
    [LAUNCHER],
    pathex=[str(ROOT / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DT_Analyser",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="DT_Analyser",
)
