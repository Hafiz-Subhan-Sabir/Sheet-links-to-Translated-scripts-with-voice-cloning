from fastapi import APIRouter, HTTPException

from app.models.schemas import DocsCreateRequest, DocsCreateResponse, SheetsAppendRequest
from app.services.auth import get_credentials
from app.services.google_integrations import (
    append_to_registry_sheet,
    create_google_doc,
    ensure_registry_spreadsheet,
)
from app.services.storage import storage

router = APIRouter(prefix="/api", tags=["google"])


@router.post("/docs/create", response_model=DocsCreateResponse)
def create_doc(body: DocsCreateRequest):
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")

    admin_cfg = storage.get_admin_config()
    folder_id = admin_cfg.get("docs_folder_id")

    try:
        doc_id, doc_url = create_google_doc(
            title=body.title,
            transcript=body.transcript,
            date=body.date,
            time=body.time,
            source_video=body.source_video,
            language=body.language,
            notes=body.notes,
            folder_id=folder_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Google Doc: {e}") from e

    sheet_logged = False
    sheet_warning = None

    if body.log_to_sheet:
        try:
            sheet_url = ensure_registry_spreadsheet()
        except Exception:
            sheet_url = admin_cfg.get("sheet_url")
        if not sheet_url:
            sheet_warning = "Registry sheet not available — doc saved but not logged"
        else:
            try:
                sheet_url = append_to_registry_sheet(
                    sheet_url=sheet_url,
                    title=body.title,
                    doc_url=doc_url,
                    date=body.date,
                    time=body.time,
                    source_video=body.source_video,
                    language=body.language,
                )
                sheet_logged = True
            except Exception as e:
                sheet_warning = f"Doc created but sheet logging failed: {e}"

    return DocsCreateResponse(
        doc_id=doc_id,
        doc_url=doc_url,
        sheet_logged=sheet_logged,
        sheet_warning=sheet_warning,
    )


@router.post("/sheets/append")
def append_sheet_row(body: SheetsAppendRequest):
    if not get_credentials():
        raise HTTPException(status_code=401, detail="Google account not connected")

    sheet_url = storage.get_admin_config().get("sheet_url")
    if not sheet_url:
        raise HTTPException(status_code=400, detail="Admin sheet not configured")

    try:
        append_to_sheet(
            sheet_url=sheet_url,
            title=body.title,
            doc_url=body.doc_url,
            date=body.date,
            time=body.time,
            source_video=body.source_video,
            language=body.language,
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
