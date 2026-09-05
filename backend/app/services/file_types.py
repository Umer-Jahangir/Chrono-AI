from dataclasses import dataclass
import re


@dataclass(frozen=True)
class FileTypeMatch:
    key: str
    mime_types: tuple[str, ...]


FILE_TYPE_MIME_MAP: dict[str, tuple[str, ...]] = {
    "pdf": ("application/pdf",),
    "text": ("text/plain",),
    "csv": ("text/csv",),
    "json": ("application/json",),
    "markdown": ("text/markdown", "text/x-markdown"),
    "word": (
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ),
    "google_docs": ("application/vnd.google-apps.document",),
    "excel": (
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ),
    "google_sheets": ("application/vnd.google-apps.spreadsheet",),
    "powerpoint": (
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ),
    "google_slides": ("application/vnd.google-apps.presentation",),
    "image": (
        "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp",
        "image/tiff", "image/svg+xml", "image/heic", "image/heif",
    ),
    "audio": (
        "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "audio/ogg",
        "audio/webm", "audio/flac", "audio/aac",
    ),
    "video": (
        "video/mp4", "video/mpeg", "video/quicktime", "video/x-msvideo",
        "video/webm", "video/ogg",
    ),
}

# Natural category words cover both uploaded Microsoft files and their native
# Google Drive equivalents.  Specific product phrases above still select one
# exact family.
FILE_TYPE_MIME_MAP.update({
    "document": (
        FILE_TYPE_MIME_MAP["word"] + FILE_TYPE_MIME_MAP["google_docs"]
        + FILE_TYPE_MIME_MAP["pdf"] + FILE_TYPE_MIME_MAP["text"]
        + FILE_TYPE_MIME_MAP["markdown"]
    ),
    "spreadsheet": FILE_TYPE_MIME_MAP["excel"] + FILE_TYPE_MIME_MAP["google_sheets"],
    "presentation": FILE_TYPE_MIME_MAP["powerpoint"] + FILE_TYPE_MIME_MAP["google_slides"],
})

# Ordered from the most specific phrases to broader category language.
_FILE_TYPE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("google_docs", re.compile(r"\bgoogle\s+(?:doc|docs|document|documents)\b", re.I)),
    ("google_sheets", re.compile(r"\bgoogle\s+(?:sheet|sheets|spreadsheet|spreadsheets)\b", re.I)),
    ("google_slides", re.compile(r"\bgoogle\s+(?:slide|slides|presentation|presentations)\b", re.I)),
    ("markdown", re.compile(r"\b(?:markdown|md)\s*(?:file|files|document|documents)?\b", re.I)),
    ("powerpoint", re.compile(r"\b(?:power\s*point|pptx?|slide\s*deck|slide\s*decks)\b", re.I)),
    ("word", re.compile(r"\b(?:microsoft\s+word|word\s+(?:file|files|document|documents)|docx?)\b", re.I)),
    ("excel", re.compile(r"\b(?:microsoft\s+excel|excel\s+(?:file|files|spreadsheet|spreadsheets)|xlsx?)\b", re.I)),
    ("pdf", re.compile(r"\bpdfs?\b", re.I)),
    ("text", re.compile(r"\b(?:txt|text\s+(?:file|files|document|documents))\b", re.I)),
    ("csv", re.compile(r"\bcsvs?\b", re.I)),
    ("json", re.compile(r"\bjson\s*(?:file|files|document|documents)?\b", re.I)),
    ("image", re.compile(r"\b(?:image|images|photo|photos|picture|pictures)\b", re.I)),
    ("audio", re.compile(r"\b(?:audio|audios|sound|sounds|recording|recordings)\b", re.I)),
    ("video", re.compile(r"\b(?:video|videos|movie|movies)\b", re.I)),
    ("document", re.compile(r"\bdocuments?\b", re.I)),
    ("spreadsheet", re.compile(r"\bspreadsheets?\b", re.I)),
    ("presentation", re.compile(r"\bpresentations?\b", re.I)),
)

ALLOWED_MIME_TYPES = frozenset(
    mime_type.casefold()
    for values in FILE_TYPE_MIME_MAP.values()
    for mime_type in values
) | frozenset({"application/vnd.google-apps.folder"})


def normalize_mime_type(value: str) -> str:
    return value.split(";", 1)[0].strip().casefold()


def detect_file_type(question: str) -> FileTypeMatch | None:
    for key, pattern in _FILE_TYPE_PATTERNS:
        if pattern.search(question):
            return FileTypeMatch(key=key, mime_types=FILE_TYPE_MIME_MAP[key])
    return None


def is_allowed_mime_type(value: str) -> bool:
    return normalize_mime_type(value) in ALLOWED_MIME_TYPES
