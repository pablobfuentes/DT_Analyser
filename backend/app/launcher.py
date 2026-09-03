"""Single-process desktop launch: API + UI in the browser. Close the window to quit."""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}"


def _prepare_data_dir() -> None:
    if os.environ.get("LTA_DATA_DIR"):
        return
    from app.path_config import load_path_config, platform_default_data_dir

    cfg = load_path_config()
    if cfg.get("data_dir"):
        data = Path(cfg["data_dir"]).expanduser()
    else:
        data = platform_default_data_dir()
    data.mkdir(parents=True, exist_ok=True)
    os.environ["LTA_DATA_DIR"] = str(data.resolve())
    db = data / "trader_analyzer.db"
    os.environ.setdefault("LTA_DATABASE_URL", f"sqlite:///{db.resolve().as_posix()}")


def _open_browser() -> None:
    time.sleep(1.2)
    webbrowser.open(URL)


def main() -> None:
    from multiprocessing import freeze_support

    freeze_support()
    _prepare_data_dir()

    print()
    print("  DT Analyser")
    print(f"  Opening {URL}")
    print("  Leave this window open while you use the app.")
    print("  Close this window to stop.")
    print()

    threading.Thread(target=_open_browser, daemon=True).start()

    import uvicorn

    from app.main import app

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
