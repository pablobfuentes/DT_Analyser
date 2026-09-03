"""Step 10 hardening: maintenance API, weekday cron metadata, PRE_MIGRATION gating."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.migrate import pending_schema_mutations
from app.main import app
from app.services.backup.service import maybe_pre_migration_backup
from app.services.maintenance import enter_maintenance, leave_maintenance, maintenance_payload


def test_pending_schema_mutations_empty_on_current_schema(db_session):
    # In-memory create_all schema has every model table; no ALTER leftovers.
    pending = pending_schema_mutations(db_session.get_bind())
    assert pending == []


def test_maybe_pre_migration_skips_when_nothing_pending(db_session):
    assert maybe_pre_migration_backup(db_session) is None


def test_maintenance_mode_returns_clean_code():
    client = TestClient(app)
    enter_maintenance("RESTORE")
    try:
        r = client.get("/api/trades")
        assert r.status_code == 503
        body = r.json()
        assert body["code"] == "MAINTENANCE_MODE"
        assert body["error"] == "MAINTENANCE_MODE"
        health = client.get("/api/health")
        assert health.status_code == 200
        wf = client.get("/api/workflow/health")
        assert wf.status_code == 200
        assert wf.json()["maintenance_mode"] is True
    finally:
        leave_maintenance()
    assert maintenance_payload()["code"] == "MAINTENANCE_MODE"
    ok = client.get("/api/health")
    assert ok.status_code == 200
