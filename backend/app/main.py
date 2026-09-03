import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import sys

from app.api import (
    accounts,
    backups,
    dashboard,
    executions,
    excursions,
    exit_analysis,
    imports,
    journal,
    market_data,
    reports,
    research,
    reviews,
    risk,
    settings as settings_api,
    signals,
    trades,
    workflow,
)
from app.config import settings
from app.db.init_data import initialize_app
from app.importers.exceptions import ImporterError, TimezoneRequiredError
from app.spa import mount_frontend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Local Trader Analyzer", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.resolved_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(accounts.router)
app.include_router(imports.router)
app.include_router(reports.router)
app.include_router(market_data.router)
app.include_router(excursions.router)
app.include_router(exit_analysis.router)
app.include_router(trades.router)
app.include_router(executions.router)
app.include_router(signals.router)
app.include_router(risk.router)
app.include_router(research.router)
app.include_router(workflow.router)
app.include_router(journal.router)
app.include_router(reviews.router)
app.include_router(backups.router)
app.include_router(settings_api.router)


@app.middleware("http")
async def maintenance_middleware(request: Request, call_next):
    from app.services.maintenance import (
        MAINTENANCE_EXEMPT_PREFIXES,
        is_maintenance,
        maintenance_payload,
    )

    path = request.url.path
    exempt = any(path == p or path.startswith(p + "/") for p in MAINTENANCE_EXEMPT_PREFIXES)
    if is_maintenance() and not exempt:
        return JSONResponse(status_code=503, content=maintenance_payload())
    return await call_next(request)


@app.exception_handler(ImporterError)
async def importer_error_handler(_request, exc: ImporterError):
    status = 422 if isinstance(exc, TimezoneRequiredError) else 400
    return JSONResponse(status_code=status, content=exc.to_dict())


@app.on_event("startup")
def on_startup():
    initialize_app()
    if "pytest" not in sys.modules and not settings.disable_automation:
        from app.services.automation.ownership import try_acquire_automation_ownership
        from app.services.automation.scheduler import start_scheduler
        from app.services.automation.watcher import start_watcher
        from app.services.automation.worker import start_worker

        if try_acquire_automation_ownership():
            start_worker()
            start_watcher()
            start_scheduler()
        else:
            logger.warning(
                "STANDBY: another process owns automation for this data directory. "
                "HTTP is available; watcher/worker/scheduler will not start."
            )
    elif settings.disable_automation:
        logger.info("Automation disabled (LTA_DISABLE_AUTOMATION=true)")
    logger.info("Local Trader Analyzer started")


@app.on_event("shutdown")
def on_shutdown():
    if "pytest" not in sys.modules and not settings.disable_automation:
        from app.services.automation.ownership import is_automation_owner, release_automation_ownership
        from app.services.automation.scheduler import stop_scheduler
        from app.services.automation.watcher import stop_watcher
        from app.services.automation.worker import stop_worker

        if is_automation_owner():
            stop_scheduler()
            stop_watcher()
            stop_worker()
        release_automation_ownership()


@app.get("/api/health")
def health():
    return {"status": "ok"}


mount_frontend(app)
