# Windows .exe

The app is a local program. A non-technical user should get a zip, extract it, and double-click `DT_Analyser.exe`.

## What she does

1. Extract `DT_Analyser.zip`.
2. Open the folder. Double-click `DT_Analyser.exe`.
3. Leave the black window open.
4. Use the app in the browser (`http://127.0.0.1:8765` if the browser does not open).
5. Close the black window when finished.

If Windows SmartScreen appears: **More info** → **Run anyway**.

Data is stored in `%LOCALAPPDATA%\LocalTraderAnalyzer` (not in the zip folder).

## What you build

From the repo root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

Output: `packaging\dist\DT_Analyser.zip`

Send that zip. First build can take several minutes (numpy/scipy/polars).

Or on GitHub: **Actions** → **Windows .exe** → **Run workflow**, then download the artifact.

The `.exe` is not signed. Antivirus may flag PyInstaller binaries; that is common for unsigned Python packs.
