import re
from urllib.parse import urlsplit


APPROVED_DRIVE_HOSTS = frozenset({"drive.google.com", "docs.google.com"})
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{5,}\d)(?!\w)")
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"(?i)\b(?:bearer|api[_ -]?key|access[_ -]?token)\s*[:=]?\s*[A-Za-z0-9._~-]{12,}"),
)
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def safe_drive_open_url(value: object) -> str | None:
    """Return only an exact-host, credential-free Google Drive HTTPS URL."""
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if any(ord(character) < 32 for character in value):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname not in APPROVED_DRIVE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path
    ):
        return None
    return value


def redact_public_text(value: object) -> str:
    """Redact common contact details and obvious credentials at the response boundary."""
    text = str(value or "")
    text = _EMAIL_RE.sub("[REDACTED EMAIL]", text)

    def redact_phone(match: re.Match[str]) -> str:
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        if _ISO_DATE_RE.fullmatch(candidate) or not 7 <= len(digits) <= 15:
            return candidate
        return "[REDACTED PHONE]"

    text = _PHONE_RE.sub(redact_phone, text)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED SECRET]", text)
    return text
