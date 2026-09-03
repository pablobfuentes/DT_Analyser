"""Step 10 — journal, tags, screenshots, search."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import settings
from app.db.models.journal import JournalAttachment, JournalEntry
from app.services.journal.attachments import delete_attachment, store_attachment
from app.services.journal.service import search_journal, upsert_trade_note
from tests.dashboard_helpers import make_trade

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    (tmp_path / "screenshots").mkdir()
    return tmp_path


def test_trade_note_and_tags(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, ticker="J1")
    db_session.commit()
    entry = upsert_trade_note(db_session, t.id, {
        "body": "chased the open",
        "followed_plan": "NO",
        "prompt_fields": {"Why I Entered": "FOMO"},
        "tags": ["FOMO", "fomo", "LATE_ENTRY"],
    })
    assert entry.followed_plan == "NO"
    hits = search_journal(db_session, "FOMO")
    assert any(h["id"] == entry.id for h in hits)
    hits2 = search_journal(db_session, "chased")
    assert any(h["id"] == entry.id for h in hits2)


def test_screenshot_hash_no_overwrite(db_session, manual_account, data_dir):
    t = make_trade(db_session, manual_account.id, ticker="J2")
    db_session.commit()
    a = store_attachment(db_session, PNG, "chart.png", trade_id=t.id)
    assert ".." not in a.relative_path
    assert a.relative_path.startswith("screenshots/")
    assert a.original_filename == "chart.png"
    b = store_attachment(db_session, PNG, "copy.png", trade_id=t.id, caption="dup")
    assert a.sha256 == b.sha256
    assert a.relative_path == b.relative_path
    root = data_dir / a.relative_path
    assert root.exists()
    delete_attachment(db_session, a.id)
    assert (data_dir / b.relative_path).exists()
    delete_attachment(db_session, b.id)
    assert not (data_dir / b.relative_path).exists()


def test_rejects_non_image(db_session, manual_account, data_dir):
    t = make_trade(db_session, manual_account.id, ticker="J3")
    db_session.commit()
    with pytest.raises(ValueError):
        store_attachment(db_session, b"MZ\x90\x00not-an-image", "tool.exe", trade_id=t.id)


def test_rejects_traversal_absolute_double_ext_and_renamed_exe(db_session, manual_account, data_dir):
    t = make_trade(db_session, manual_account.id, ticker="J4")
    db_session.commit()
    with pytest.raises(ValueError, match="traversal"):
        store_attachment(db_session, PNG, "../../evil.png", trade_id=t.id)
    with pytest.raises(ValueError, match="Absolute"):
        store_attachment(db_session, PNG, "C:/temp/chart.png", trade_id=t.id)
    with pytest.raises(ValueError, match="Double"):
        store_attachment(db_session, PNG, "photo.jpg.png", trade_id=t.id)
    with pytest.raises(ValueError):
        store_attachment(db_session, PNG, "image.png.exe", trade_id=t.id)
    with pytest.raises(ValueError, match="Only PNG"):
        store_attachment(db_session, b"MZ\x90\x00not-an-image", "nice.png", trade_id=t.id)
    # Content-Type is not an argument; magic bytes + extension are both required.
    store_attachment(db_session, PNG, "ok.PNG", trade_id=t.id)
