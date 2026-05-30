"""Input validation shared by the CLI and the web layer.

Centralizes limits and sanitization so neither front end can drive the back end
into malformed API calls, oversized payloads, CSV-injection in exported logs, or
excessive fan-out against the remote Rossum API. The web layer is the only
network-exposed surface, so its inputs (connection details + posted rows) are
validated here before any value reaches the SDK.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# --- Limits (conservative; the grid is operator-facing, not public) ---
MAX_MANUAL_ADD_ROWS = 100         # rows the grid adds in one "Add" action
MAX_ROWS = 1000                   # rows accepted per load (fan-out / memory guard)
MAX_FIELD_LEN = 1000              # per-field character cap
MAX_TOKEN_LEN = 1024
MAX_URL_LEN = 2048
MAX_ORG_ID = 100_000_000_000      # 1e11
MAX_REQUEST_BYTES = 5 * 1024 * 1024  # cap on the /load request body (DoS guard)

# Columns the loader understands (mirrors core.SUPPORTED_COLUMNS + "action").
# Kept independent so the web layer never imports the Rossum SDK; a test asserts
# this stays in sync with core.
ALLOWED_ROW_KEYS = (
    "auth_type", "email", "first_name", "last_name", "username",
    "oidc_id", "role", "queue_ids", "can_approve", "action",
)

# Field values may keep tab/newline/CR (queue_ids is multi-line); all other
# C0 control chars and DEL are stripped. Tokens/URLs forbid ALL control chars.
_FIELD_BAD_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ANY_CTRL = re.compile(r"[\x00-\x1f\x7f]")


class ValidationError(ValueError):
    """Raised when an input fails validation (message is safe to show)."""


def validate_token(token: str) -> str:
    token = (token or "").strip()
    if not token:
        raise ValidationError("API token is required.")
    if len(token) > MAX_TOKEN_LEN:
        raise ValidationError(f"API token is too long (max {MAX_TOKEN_LEN} characters).")
    if _ANY_CTRL.search(token) or any(c.isspace() for c in token):
        raise ValidationError("API token contains whitespace or control characters.")
    return token


def validate_domain(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValidationError("Domain URL is required.")
    if len(url) > MAX_URL_LEN:
        raise ValidationError(f"Domain URL is too long (max {MAX_URL_LEN} characters).")
    if _ANY_CTRL.search(url):
        raise ValidationError("Domain URL contains control characters.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValidationError("Domain URL must start with http:// or https://.")
    if not parsed.netloc:
        raise ValidationError("Domain URL is missing a host.")
    return url.rstrip("/")


def validate_org_id(value: str) -> str:
    value = (value or "").strip()
    if not value.isdigit():
        raise ValidationError("Organization ID must be digits only.")
    n = int(value)
    if n <= 0 or n > MAX_ORG_ID:
        raise ValidationError(f"Organization ID must be between 1 and {MAX_ORG_ID}.")
    return str(n)


def clean_field(value) -> str:
    """Coerce a row value to a safe, length-checked string."""
    if value is None:
        return ""
    if not isinstance(value, (str, int, float, bool)):
        raise ValidationError("field has an unsupported value type")
    s = str(value)
    if len(s) > MAX_FIELD_LEN:
        raise ValidationError(f"field is too long (max {MAX_FIELD_LEN} characters)")
    return _FIELD_BAD_CTRL.sub("", s)


def validate_rows(rows) -> list[dict]:
    """Validate and sanitize a posted rows payload.

    rows must be a list of objects, capped at MAX_ROWS (fan-out / DoS guard);
    unknown keys are dropped; values are coerced to strings, length-capped, and
    stripped of dangerous control characters. Raises ValidationError on
    clearly-bad input (the caller returns HTTP 400).
    """
    if not isinstance(rows, list):
        raise ValidationError("'rows' must be a list.")
    if len(rows) > MAX_ROWS:
        raise ValidationError(
            f"Too many rows ({len(rows)}); the maximum per load is {MAX_ROWS}."
        )
    allowed = set(ALLOWED_ROW_KEYS)
    cleaned_rows: list[dict] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError(f"Row {i + 1} is not an object.")
        cleaned: dict = {}
        for key, value in row.items():
            if key not in allowed:
                continue  # silently drop unknown keys
            try:
                cleaned[key] = clean_field(value)
            except ValidationError as exc:
                raise ValidationError(f"Row {i + 1}, field '{key}': {exc}") from None
        cleaned_rows.append(cleaned)
    return cleaned_rows
