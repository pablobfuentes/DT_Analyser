from pathlib import Path

from app.path_config import load_path_config, path_config_file, save_path_config
from app.paths import data_layout, resolve_data_dir


def test_path_config_roundtrip(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr("app.path_config.platform_default_data_dir", lambda: cfg)
    monkeypatch.setattr("app.paths.platform_default_data_dir", lambda: cfg)

    assert load_path_config() == {}
    data = tmp_path / "trading"
    save_path_config({"data_dir": str(data), "inbox": str(tmp_path / "custom_inbox")})
    assert path_config_file().is_file()
    loaded = load_path_config()
    assert loaded["data_dir"] == str(data)
    assert "inbox" in loaded

    monkeypatch.setattr("app.config.settings.data_dir", None)
    # Avoid ./data preference if present in cwd during tests
    monkeypatch.chdir(tmp_path)
    assert resolve_data_dir() == data.resolve()
    layout = data_layout()
    assert layout["inbox"] == (tmp_path / "custom_inbox").resolve()
    assert layout["backups"] == (data / "backups").resolve()
