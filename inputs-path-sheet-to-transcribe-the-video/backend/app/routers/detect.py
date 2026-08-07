from fastapi import APIRouter

from app.models.schemas import (
    DetectSourceRequest,
    DetectSourceResponse,
    FindLocalFileRequest,
    FindLocalFileResponse,
)
from app.services.detect_source import detect_source, find_local_files_by_name

router = APIRouter(prefix="/api", tags=["detect"])


@router.post("/detect-source", response_model=DetectSourceResponse)
def detect_source_endpoint(body: DetectSourceRequest) -> DetectSourceResponse:
    result = detect_source(body.value)
    return DetectSourceResponse(**result)


@router.post("/local/find", response_model=FindLocalFileResponse)
def find_local_file_endpoint(body: FindLocalFileRequest) -> FindLocalFileResponse:
    matches = find_local_files_by_name(body.filename)
    return FindLocalFileResponse(filename=body.filename, matches=matches)
