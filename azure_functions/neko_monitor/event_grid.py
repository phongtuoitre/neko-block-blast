from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit


BLOB_CREATED_EVENT_TYPE = "Microsoft.Storage.BlobCreated"
_SENSITIVE_LOG_FRAGMENTS = (
    "accountkey=",
    "connectionstring",
    "password=",
    "secret=",
    "sharedaccesssignature",
    "sig=",
    "signature=",
    "token=",
)


@dataclass(frozen=True)
class BlobUploadEventGridInfo:
    should_process: bool
    event_id: str
    event_type: str
    subject: str
    event_time: str
    blob_url: str
    api: str
    content_type: str
    content_length: int | None


def build_blob_upload_eventgrid_info(event: Any) -> BlobUploadEventGridInfo:
    event_type = _safe_text(getattr(event, "event_type", ""))
    data = _safe_event_data(event)
    return BlobUploadEventGridInfo(
        should_process=event_type == BLOB_CREATED_EVENT_TYPE,
        event_id=_safe_text(getattr(event, "id", "")),
        event_type=event_type,
        subject=_safe_text(getattr(event, "subject", "")),
        event_time=_safe_event_time(getattr(event, "event_time", "")),
        blob_url=safe_blob_url_for_log(data.get("url")),
        api=_safe_text(data.get("api")),
        content_type=_safe_text(data.get("contentType")),
        content_length=_safe_content_length(data.get("contentLength")),
    )


def safe_blob_url_for_log(value: Any) -> str:
    if not isinstance(value, str):
        return ""

    blob_url = value.strip()
    if not blob_url:
        return ""

    try:
        parts = urlsplit(blob_url)
    except ValueError:
        return "<redacted>" if _contains_sensitive_fragment(blob_url) else blob_url

    sanitized_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    if _contains_sensitive_fragment(sanitized_url):
        return "<redacted>"
    return sanitized_url


def _safe_event_data(event: Any) -> dict[str, Any]:
    try:
        data = event.get_json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_event_time(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return _safe_text(value)


def _safe_content_length(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        content_length = int(value)
    except (TypeError, ValueError):
        return None
    return content_length if content_length >= 0 else None


def _contains_sensitive_fragment(value: str) -> bool:
    normalized_value = value.casefold()
    return any(fragment in normalized_value for fragment in _SENSITIVE_LOG_FRAGMENTS)
