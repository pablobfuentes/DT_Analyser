"""Backup and restore API. Restore is never a casual one-click."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.automation.jobs import enqueue
from app.services.backup.service import list_backups, restore_preview, restore_backup, verify_backup

router = APIRouter(prefix="/api/backups", tags=["backups"])


class RestoreBody(BaseModel):
    confirm: bool = False


@router.get("")
def backups(db: Session = Depends(get_db)):
    return {"items": list_backups(db)}


@router.post("")
def create(db: Session = Depends(get_db)):
    job = enqueue(db, "BACKUP", {"backup_type": "MANUAL"})
    return {"job_id": job.id, "status": job.status}


@router.post("/{backup_id}/verify")
def verify(backup_id: str, db: Session = Depends(get_db)):
    try:
        return verify_backup(db, backup_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/{backup_id}/restore-preview")
def preview(backup_id: str, db: Session = Depends(get_db)):
    try:
        return restore_preview(db, backup_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{backup_id}/restore")
def restore(backup_id: str, body: RestoreBody, db: Session = Depends(get_db)):
    if not body.confirm:
        raise HTTPException(400, "Restore requires confirm=true")
    try:
        return restore_backup(db, backup_id, confirm=True)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
