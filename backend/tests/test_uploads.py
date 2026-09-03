"""Temp preview file lifecycle and path sanitization."""

import os
import time
from pathlib import Path

from app.config import settings
from app.db.init_data import (
    cleanup_stale_uploads,
    get_upload_path,
    sanitize_upload_filename,
    save_upload,
)


def test_sanitize_strips_parent_segments():
    assert sanitize_upload_filename("../../etc/passwd") == "passwd"
    assert sanitize_upload_filename("C:\\\\temp\\\\x.csv") == "x.csv"
    assert sanitize_upload_filename("") == "upload.csv"


def test_save_upload_cannot_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    dest, file_hash = save_upload(b"abc,def\n", "../../secret.csv")
    assert dest.name == "secret.csv"
    assert dest.parent.parent.resolve() == tmp_path.resolve()
    assert file_hash == dest.parent.name


def test_get_upload_path_rejects_non_hash():
    assert get_upload_path("../nope") is None
    assert get_upload_path("abc") is None


def test_expired_preview_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    dest, file_hash = save_upload(b"x", "a.csv")
    dest.unlink()
    dest.parent.rmdir()
    assert get_upload_path(file_hash) is None


def test_stale_hash_dirs_are_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    stale_hash = "a" * 64
    stale = tmp_path / stale_hash
    stale.mkdir()
    (stale / "old.csv").write_text("old", encoding="utf-8")
    old = time.time() - 25 * 3600
    os.utime(stale, (old, old))

    fresh_hash = "b" * 64
    fresh = tmp_path / fresh_hash
    fresh.mkdir()
    (fresh / "new.csv").write_text("new", encoding="utf-8")

    outsider = tmp_path / "not-a-hash-dir"
    outsider.mkdir()
    (outsider / "keep.csv").write_text("keep", encoding="utf-8")

    removed = cleanup_stale_uploads(max_age_seconds=24 * 3600)
    assert removed == 1
    assert not stale.exists()
    assert fresh.exists()
    assert (outsider / "keep.csv").exists()
