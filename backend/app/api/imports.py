import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.init_data import get_upload_path, save_upload
from app.db.models.import_batch import ImportBatch
from app.db.session import get_db
from app.importers.detector import preview_file
from app.importers.exceptions import ImporterError
from app.schemas import ImportBatchResponse, ImportCommitResponse, ImportPreviewResponse
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    parser_name: str | None = Form(None),
    timezone: str | None = Form(None),
    db: Session = Depends(get_db),
):
    content = await file.read()
    path, file_hash = save_upload(content, file.filename or "upload.csv")

    result = preview_file(path, parser_name, timezone)

    duplicate_warning = None
    prior = db.query(ImportBatch).filter(ImportBatch.file_hash == file_hash).first()
    if prior:
        duplicate_warning = (
            "This file hash was imported before; identical executions/trades will be skipped."
        )

    if isinstance(result, dict) and result.get("error"):
        warnings = []
        if duplicate_warning:
            warnings.append(duplicate_warning)
        return ImportPreviewResponse(
            filename=file.filename or "upload.csv",
            file_hash=file_hash,
            error=result.get("error"),
            message=result.get("message"),
            detected_columns=result.get("detected_columns", []),
            options=result.get("options"),
            warnings=warnings,
        )

    warnings = list(result.warnings)
    if duplicate_warning:
        warnings.insert(0, duplicate_warning)

    return ImportPreviewResponse(
        filename=file.filename or "upload.csv",
        file_hash=file_hash,
        detected_source_type=result.source_type,
        parser=result.parser_name,
        confidence=result.confidence,
        detected_columns=result.detected_columns,
        row_count=result.row_count,
        timezone_status=result.timezone_status,
        sample_normalized_records=result.sample_records,
        warnings=warnings,
        errors=result.errors,
    )


@router.post("/commit", response_model=ImportCommitResponse)
async def commit_import(
    file: UploadFile | None = File(None),
    file_hash: str | None = Form(None),
    account_id: int = Form(...),
    parser_name: str = Form(...),
    timezone: str | None = Form(None),
    db: Session = Depends(get_db),
):
    path = None
    filename = "upload.csv"

    if file is not None:
        content = await file.read()
        path, computed_hash = save_upload(content, file.filename or "upload.csv")
        filename = file.filename or "upload.csv"
        file_hash = computed_hash
    elif file_hash:
        path = get_upload_path(file_hash)
        if path:
            filename = path.name
    else:
        raise HTTPException(status_code=400, detail="file or file_hash required")

    if path is None or not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "PREVIEW_EXPIRED",
                "message": "Upload not found or preview expired; please re-upload the file.",
            },
        )

    try:
        service = ImportService(db)
        stats = service.commit_import(path, filename, account_id, parser_name, timezone)
        return ImportCommitResponse(**stats)
    except ImporterError:
        raise
    except Exception as e:
        logger.exception("Import commit failed")
        raise HTTPException(status_code=500, detail={"error": "IMPORT_FAILED", "message": str(e)})


@router.get("", response_model=list[ImportBatchResponse])
def list_imports(db: Session = Depends(get_db)):
    return db.query(ImportBatch).order_by(ImportBatch.id.desc()).limit(100).all()


@router.get("/{import_id}", response_model=ImportBatchResponse)
def get_import(import_id: int, db: Session = Depends(get_db)):
    batch = db.get(ImportBatch, import_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return batch
