from pathlib import Path

from app.spa import frontend_dist, bundle_root


def test_bundle_root_is_repo_in_dev():
    root = bundle_root()
    assert (root / "backend" / "app" / "main.py").is_file()


def test_frontend_dist_none_or_has_index():
    dist = frontend_dist()
    if dist is None:
        return
    assert (dist / "index.html").is_file()
