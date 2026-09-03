from typing import Literal, Optional

from pydantic import BaseModel, Field


class DetectSourceRequest(BaseModel):
    value: str


class DetectSourceResponse(BaseModel):
    type: Optional[Literal["local", "online"]] = None
    normalized: str = ""
    valid: bool = False
    message: Optional[str] = None


class TranscribeRequest(BaseModel):
    source: str
    type: Literal["local", "online"]
    language: Optional[str] = None
    upload_id: Optional[str] = None
    prefetch_cache_id: Optional[str] = None


class PrefetchRequest(BaseModel):
    url: str


class PrefetchStatusResponse(BaseModel):
    cache_id: str
    url: str
    status: str
    duration: float = 0.0
    progress: float = 0.0
    error: Optional[str] = None
    ready: bool = False


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    confidence: Optional[float] = None


class TranscribeResponse(BaseModel):
    transcript: str
    segments: list[TranscriptSegment]
    language: str
    duration: float
    confidence: Optional[float] = None
    job_id: Optional[str] = None


class TranslateRequest(BaseModel):
    text: str
    target_language: str
    source_language: Optional[str] = None


class TranslateResponse(BaseModel):
    translated_text: str
    provider: Literal["google_api", "google_free"] = "google_free"


class AuthStatusResponse(BaseModel):
    connected: bool
    email: Optional[str] = None
    sheet_ready: bool = False
    sheet_url: Optional[str] = None
    output_sheet_url: Optional[str] = None
    oauth_configured: bool = False


class DocsCreateRequest(BaseModel):
    title: str
    transcript: str
    date: str
    time: str
    source_video: str
    language: str
    notes: Optional[str] = None
    log_to_sheet: bool = True


class DocsCreateResponse(BaseModel):
    doc_id: str
    doc_url: str
    sheet_logged: bool
    sheet_warning: Optional[str] = None


class SheetsAppendRequest(BaseModel):
    title: str
    doc_url: str
    date: str
    time: str
    source_video: str
    language: str


class AdminUnlockRequest(BaseModel):
    password: str


class AdminUnlockResponse(BaseModel):
    success: bool
    message: Optional[str] = None


class AdminConfigRequest(BaseModel):
    sheet_url: str
    output_sheet_url: Optional[str] = None
    docs_folder_id: Optional[str] = None
    voice_output_dir: Optional[str] = None


class AdminConfigResponse(BaseModel):
    success: bool
    sheet_url: Optional[str] = None
    output_sheet_url: Optional[str] = None
    docs_folder_id: Optional[str] = None
    voice_output_dir: Optional[str] = None


class AdminConfigStatusResponse(BaseModel):
    configured: bool
    output_configured: bool = False
    locked: bool
    sheet_url_masked: str = "••••••••••"
    output_sheet_url_masked: str = ""
    sheet_url: Optional[str] = None
    output_sheet_url: Optional[str] = None
    docs_folder_id: Optional[str] = None
    voice_output_dir: Optional[str] = None


class PipelineRunRequest(BaseModel):
    source: str
    type: Literal["local", "online"]
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    title: str
    date: str
    time: str
    notes: Optional[str] = None
    upload_id: Optional[str] = None
    log_to_sheet: bool = True


class PipelineRunResponse(BaseModel):
    transcript: str
    translated_text: Optional[str] = None
    doc_url: Optional[str] = None
    sheet_logged: bool = False
    language: str
    duration: float


class AutoPipelineRunRequest(BaseModel):
    source: str
    type: Literal["local", "online"]
    source_language: Optional[str] = None
    title: Optional[str] = None
    upload_id: Optional[str] = None
    prefetch_cache_id: Optional[str] = None


class AutoPipelineRunResponse(BaseModel):
    title: str
    transcript: str
    translations: dict[str, str] = Field(default_factory=dict)
    detected_language: str
    doc_url: str
    sheet_url: str
    sheet_logged: bool
    sheet_warning: Optional[str] = None
    duration: float


class PipelineFinishRequest(BaseModel):
    source: str
    transcript: str
    detected_language: str
    duration: float = 0.0
    title: Optional[str] = None
    upload_filename: Optional[str] = None
    target_languages: list[str] = Field(default_factory=list)


class PipelineFinishStartResponse(BaseModel):
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    step: str = ""
    progress: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    path: str


class FindLocalFileRequest(BaseModel):
    filename: str


class FindLocalFileResponse(BaseModel):
    filename: str
    matches: list[str] = Field(default_factory=list)


class UploadInitRequest(BaseModel):
    filename: str
    size: int = 0


class UploadInitResponse(BaseModel):
    upload_id: str
    chunk_size: int


class UploadCompleteRequest(BaseModel):
    upload_id: str
    filename: str
    total_chunks: int


class BatchRowResponse(BaseModel):
    row_index: int
    program_title: str
    video_path: str
    status: str
    error: Optional[str] = None


class BatchQueueResponse(BaseModel):
    rows: list[BatchRowResponse] = Field(default_factory=list)
    pending_count: int = 0
    processing_count: int = 0
    done_count: int = 0
    failed_count: int = 0
    total_count: int = 0
    input_sheet_url: Optional[str] = None
    output_sheet_url: Optional[str] = None


class BatchConfigResponse(BaseModel):
    input_sheet_configured: bool
    output_sheet_configured: bool = False
    input_sheet_url_masked: str = ""
    output_sheet_url_masked: str = ""
    input_sheet_url: Optional[str] = None
    output_sheet_url: Optional[str] = None
    google_connected: bool = False
    batch_workers: int = 3
    elevenlabs_configured: bool = False
    voice_output_dir: Optional[str] = None


class BatchRunResponse(BaseModel):
    job_id: str
    pending_count: int
    batch_workers: int = 3


class OutputRowResponse(BaseModel):
    row_index: int
    video_name: str
    source_video: str = ""
    category: str = ""
    video_length: str = ""
    date_transcribed: str = ""
    docs_link: str = ""
    status: str = ""
    voice_name: str = ""
    voice_directory: str = ""
    voice_notes: str = ""
    error: Optional[str] = None


class OutputQueueResponse(BaseModel):
    rows: list[OutputRowResponse] = Field(default_factory=list)
    ready_for_voice_count: int = 0
    voice_cloned_count: int = 0
    marked_done_count: int = 0
    total_count: int = 0
    output_sheet_url: Optional[str] = None


class VoiceInfo(BaseModel):
    id: str
    name: str
    provider_voice_id: str
    created_at: str
    sample_filename: Optional[str] = None


class VoiceListResponse(BaseModel):
    voices: list[VoiceInfo] = Field(default_factory=list)
    voice_output_dir: Optional[str] = None
    elevenlabs_configured: bool = False


class VoiceCloneCreateResponse(BaseModel):
    voice: VoiceInfo


class VoiceSynthesizeRequest(BaseModel):
    voice_id: str  # local DB id, or "new" handled separately
    output_row_indexes: list[int] = Field(default_factory=list)
    language_column: str = "English Transcript"
    output_dir: Optional[str] = None


class VoiceSynthesizeResponse(BaseModel):
    job_id: str


class SpeakTextRequest(BaseModel):
    voice_id: str
    text: str
    title: str = "spoken"
    output_dir: Optional[str] = None


class VoiceCloneFromUrlRequest(BaseModel):
    url: str
    name: str = ""
    start_sec: float = 0.0
    duration_sec: float = 30.0


class VoiceCloneFromUrlResponse(BaseModel):
    job_id: str


class MarkDoneRequest(BaseModel):
    output_row_indexes: list[int] = Field(default_factory=list)


class MarkDoneResponse(BaseModel):
    updated: int


class SheetHistoryItem(BaseModel):
    url: str
    title: str = ""
    used_at: str = ""


class SheetSessionResponse(BaseModel):
    email: Optional[str] = None
    input_url: Optional[str] = None
    output_url: Optional[str] = None
    input_history: list[SheetHistoryItem] = Field(default_factory=list)
    output_history: list[SheetHistoryItem] = Field(default_factory=list)
    created_input: bool = False
    created_output: bool = False


class SheetUseRequest(BaseModel):
    kind: Literal["input", "output"]
    url: str
    title: str = ""


class SheetCreateRequest(BaseModel):
    kind: Literal["input", "output"]

