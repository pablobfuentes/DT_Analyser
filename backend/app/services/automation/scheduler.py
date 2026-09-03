"""EOD scheduler. Enqueues persistent jobs; does not run pipeline logic."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import settings
from app.services.preferences import get_pref
from app.utils.analytics import analytics_tz

logger = logging.getLogger(__name__)

_scheduler = None


def parse_eod_time(value: str | None) -> tuple[int, int]:
    if not value:
        return settings.eod_finalize_hour, settings.eod_finalize_minute
    parts = value.split(":")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def next_eod_utc(after: datetime, hour: int, minute: int, tz: ZoneInfo | None = None) -> datetime:
    """Next wall-clock EOD in America/New_York, returned as UTC. DST-safe."""
    zone = tz or analytics_tz()
    if after.tzinfo is None:
        after = after.replace(tzinfo=ZoneInfo("UTC"))
    local = after.astimezone(zone)
    candidate = datetime.combine(local.date(), time(hour, minute), tzinfo=zone)
    if candidate <= local:
        candidate = datetime.combine(local.date() + timedelta(days=1), time(hour, minute), tzinfo=zone)
    # Weekday-only. No exchange-holiday calendar; a holiday run may no-op.
    while candidate.weekday() >= 5:
        candidate = datetime.combine(candidate.date() + timedelta(days=1), time(hour, minute), tzinfo=zone)
    return candidate.astimezone(ZoneInfo("UTC"))


def _enqueue_finalize() -> None:
    from app.db.session import SessionLocal
    from app.services.automation.jobs import enqueue
    from app.utils.analytics import ny_date_from_utc
    from app.utils.clock import utc_now

    db = SessionLocal()
    try:
        if not get_pref(db, "eod_finalize_enabled", settings.eod_finalize_enabled):
            return
        ny = ny_date_from_utc(utc_now()).isoformat()
        enqueue(db, "FINALIZE_DAY", {"date": ny}, coalesce_type=True)
        logger.info("Enqueued FINALIZE_DAY for %s", ny)
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("APScheduler not installed; EOD schedule disabled. Use CLI finalize_day.")
        return

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        hh, mm = parse_eod_time(get_pref(db, "eod_finalize_time"))
        enabled = get_pref(db, "eod_finalize_enabled", settings.eod_finalize_enabled)
    finally:
        db.close()

    if not enabled:
        logger.info("EOD scheduler disabled by preference")
        return

    sched = BackgroundScheduler(timezone=str(analytics_tz()))
    sched.add_job(
        _enqueue_finalize,
        CronTrigger(day_of_week="mon-fri", hour=hh, minute=mm, timezone=str(analytics_tz())),
        id="eod_finalize",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    logger.info("EOD scheduler started Mon–Fri at %02d:%02d %s", hh, mm, analytics_tz())


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_alive() -> bool:
    return bool(_scheduler and _scheduler.running)
