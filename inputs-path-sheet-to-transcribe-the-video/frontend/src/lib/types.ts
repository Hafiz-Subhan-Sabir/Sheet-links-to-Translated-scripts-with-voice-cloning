export type SourceType = "local" | "online";

export interface DetectSourceResponse {
  type: SourceType | null;
  normalized: string;
  valid: boolean;
  message?: string | null;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  confidence?: number | null;
}

export interface TranscribeResponse {
  transcript: string;
  segments: TranscriptSegment[];
  language: string;
  duration: number;
  confidence?: number | null;
  job_id?: string | null;
}

export interface TranslateResponse {
  translated_text: string;
  provider?: "google_api" | "google_free";
}

export interface AuthStatusResponse {
  connected: boolean;
  email?: string | null;
  sheet_ready?: boolean;
  sheet_url?: string | null;
  output_sheet_url?: string | null;
  oauth_configured?: boolean;
}

export interface DocsCreateResponse {
  doc_id: string;
  doc_url: string;
  sheet_logged: boolean;
  sheet_warning?: string | null;
}

export interface AdminConfigStatusResponse {
  configured: boolean;
  output_configured?: boolean;
  locked: boolean;
  sheet_url_masked?: string;
  output_sheet_url_masked?: string;
  sheet_url?: string | null;
  output_sheet_url?: string | null;
  docs_folder_id?: string | null;
  voice_output_dir?: string | null;
}

export interface BatchRow {
  row_index: number;
  program_title: string;
  video_path: string;
  status: string;
  error?: string | null;
}

export interface BatchQueueResponse {
  rows: BatchRow[];
  pending_count: number;
  processing_count?: number;
  done_count?: number;
  failed_count?: number;
  total_count: number;
  input_sheet_url?: string | null;
  output_sheet_url?: string | null;
}

export interface BatchConfigResponse {
  input_sheet_configured: boolean;
  output_sheet_configured?: boolean;
  input_sheet_url_masked: string;
  output_sheet_url_masked?: string;
  input_sheet_url?: string | null;
  output_sheet_url?: string | null;
  google_connected: boolean;
  batch_workers?: number;
  elevenlabs_configured?: boolean;
  voice_output_dir?: string | null;
}

export interface BatchRunResponse {
  job_id: string;
  pending_count: number;
  batch_workers?: number;
}

export interface BatchJobResult {
  processed: number;
  failed: number;
  cancelled?: number;
  total: number;
  workers?: number;
  errors: Array<{ row_index: number; program_title: string; error: string }>;
  output_sheet_url?: string | null;
}

export interface OutputRow {
  row_index: number;
  video_name: string;
  source_video?: string;
  category?: string;
  video_length?: string;
  date_transcribed?: string;
  docs_link?: string;
  status?: string;
  voice_name?: string;
  voice_directory?: string;
  voice_notes?: string;
  error?: string | null;
}

export interface OutputQueueResponse {
  rows: OutputRow[];
  ready_for_voice_count: number;
  voice_cloned_count: number;
  marked_done_count: number;
  total_count: number;
  output_sheet_url?: string | null;
}

export interface VoiceInfo {
  id: string;
  name: string;
  provider_voice_id: string;
  created_at: string;
  sample_filename?: string | null;
}

export interface VoiceListResponse {
  voices: VoiceInfo[];
  voice_output_dir?: string | null;
  elevenlabs_configured: boolean;
}

export interface VoiceJobResult {
  processed: number;
  failed: number;
  files: string[];
  filenames?: string[];
  output_dir: string;
  voice_name: string;
  errors: Array<{ row_index: number; error: string }>;
}

export interface VisualBeat {
  index: number;
  start_sec: number;
  end_sec: number;
  duration_sec: number;
  narration: string;
  visual_type: string;
  image_prompt: string;
  on_screen_text: string;
  camera_move: string;
  edit_note: string;
  image_filename?: string | null;
}

export interface AutoEditPackResult {
  title: string;
  pack_dir: string;
  zip_filename: string;
  mp4_filename?: string | null;
  beat_count: number;
  has_audio: boolean;
  beats: VisualBeat[];
  capcut_note: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  step: string;
  progress: number;
  result?:
    | TranscribeResponse
    | AutoPipelineResponse
    | BatchJobResult
    | VoiceJobResult
    | AutoEditPackResult
    | null;
  error?: string | null;
}

export interface PrefetchStatusResponse {
  cache_id: string;
  url: string;
  status: "idle" | "pending" | "downloading" | "ready" | "failed";
  duration: number;
  progress: number;
  error?: string | null;
  ready: boolean;
}

export interface UploadResponse {
  upload_id: string;
  filename: string;
  path: string;
}

export type PipelineStep = "input" | "transcript" | "translate" | "save" | "done";

export interface AutoPipelineResponse {
  title: string;
  transcript: string;
  translations: Record<string, string>;
  detected_language: string;
  doc_url: string;
  sheet_url: string;
  sheet_logged: boolean;
  sheet_warning?: string | null;
  duration: number;
}

export type SheetKind = "input" | "output";

export interface SheetHistoryItem {
  url: string;
  title?: string;
  used_at?: string;
}

export interface SheetSessionResponse {
  email?: string | null;
  input_url?: string | null;
  output_url?: string | null;
  input_history: SheetHistoryItem[];
  output_history: SheetHistoryItem[];
  created_input?: boolean;
  created_output?: boolean;
}
