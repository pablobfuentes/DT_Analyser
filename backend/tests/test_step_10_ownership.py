"""Inter-process automation ownership — OS file lock, not PID-only."""

from __future__ import annotations

from app.services.automation.ownership import AutomationLock, ownership_status


def test_second_process_cannot_own_same_data_dir(tmp_path):
    a = AutomationLock(tmp_path)
    b = AutomationLock(tmp_path)
    assert a.acquire() is True
    assert a.owned is True
    assert b.acquire() is False
    assert b.owned is False
    status = ownership_status(tmp_path)
    # This process holds A; status helper uses the process singleton, not A.
    a.release()
    assert b.acquire() is True
    b.release()


def test_owner_release_then_new_instance_acquires(tmp_path):
    a = AutomationLock(tmp_path)
    assert a.acquire() is True
    a.release()
    c = AutomationLock(tmp_path)
    assert c.acquire() is True
    c.release()


def test_crash_does_not_leave_permanent_stale_ownership(tmp_path):
    a = AutomationLock(tmp_path)
    assert a.acquire() is True
    lock_file = tmp_path / "automation.lock"
    assert lock_file.exists()
    a.simulate_crash()
    # Stale lock *file* may remain; OS lock must be gone.
    c = AutomationLock(tmp_path)
    assert c.acquire() is True
    c.release()
