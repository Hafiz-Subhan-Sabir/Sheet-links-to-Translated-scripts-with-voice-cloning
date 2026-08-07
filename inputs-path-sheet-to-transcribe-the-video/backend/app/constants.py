"""Shared constants for Sheet → Transcript → Translate → Voice Clone workflow."""

# Input queue sheet headers
INPUT_SHEET_HEADERS = [
    "Video Name",
    "Video Path",
    "Status",
    "Error",
]

BATCH_STATUS_PENDING = "pending"
BATCH_STATUS_PROCESSING = "processing"
BATCH_STATUS_DONE = "done"
BATCH_STATUS_FAILED = "failed"
BATCH_STATUS_VOICE_READY = "ready_for_voice"
BATCH_STATUS_VOICE_DONE = "voice_cloned"
BATCH_STATUS_MARKED_DONE = "marked_done"

# Output sheet — one row per transcribed video
# Full transcripts live in Google Docs; sheet cells hold text (truncated at SHEET_CELL_MAX)
OUTPUT_SHEET_HEADERS = [
    "Video Name",
    "Source Video",
    "English Transcript",
    "British English",
    "American English",
    "Spanish",
    "Chinese (Simplified)",
    "Hindi",
    "Arabic",
    "Portuguese",
    "French",
    "Russian",
    "Japanese",
    "German",
    "Korean",
    "Category",
    "Video Length",
    "Date Transcribed",
    "Detected Language",
    "Google Docs Link",
    "Status",
    "Voice Name",
    "Voice Directory",
    "Voice Notes",
    "Error",
]

SHEET_CELL_MAX = 49_000  # Google Sheets cell limit is 50k

# Top 10 popular languages (beyond English variants) for translation columns
TRANSLATION_LANGUAGES: list[tuple[str, str]] = [
    ("es", "Spanish"),
    ("zh-CN", "Chinese (Simplified)"),
    ("hi", "Hindi"),
    ("ar", "Arabic"),
    ("pt", "Portuguese"),
    ("fr", "French"),
    ("ru", "Russian"),
    ("ja", "Japanese"),
    ("de", "German"),
    ("ko", "Korean"),
]

VIDEO_CATEGORIES = [
    "Tech",
    "Finance",
    "Entertainment",
    "Songs / Music",
    "Education",
    "News",
    "Gaming",
    "Lifestyle",
    "Sports",
    "Health",
    "Business",
    "Comedy",
    "Other",
]

# (code, display name) — languages available for user selection / voice cloning
YOUTUBE_POPULAR_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English"),
    ("en-GB", "British English"),
    ("en-US", "American English"),
    *TRANSLATION_LANGUAGES,
    ("id", "Indonesian"),
    ("tr", "Turkish"),
    ("vi", "Vietnamese"),
    ("it", "Italian"),
    ("bn", "Bengali"),
    ("ur", "Urdu"),
    ("tl", "Filipino"),
    ("zh-TW", "Chinese (Traditional)"),
    ("pl", "Polish"),
    ("nl", "Dutch"),
    ("th", "Thai"),
    ("fa", "Persian"),
    ("ms", "Malay"),
    ("ta", "Tamil"),
    ("te", "Telugu"),
    ("uk", "Ukrainian"),
    ("el", "Greek"),
    ("he", "Hebrew"),
    ("sv", "Swedish"),
    ("ro", "Romanian"),
    ("cs", "Czech"),
    ("hu", "Hungarian"),
    ("pa", "Punjabi"),
    ("mr", "Marathi"),
    ("gu", "Gujarati"),
    ("kn", "Kannada"),
    ("ml", "Malayalam"),
    ("sw", "Swahili"),
    ("af", "Afrikaans"),
    ("no", "Norwegian"),
    ("da", "Danish"),
    ("fi", "Finnish"),
]

# Legacy aliases kept for older registry helpers
REGISTRY_SHEET_NAME = "videos transcripts"
REGISTRY_HEADERS = [
    "Title",
    "Google Docs Link",
    "Date",
    "Time",
    "Source Video",
    "Language",
    "Created At",
]
OUTPUT_DOC_TITLE = "Video Transcripts"
