from __future__ import annotations

import base64
import binascii
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


SUPPORTED_QUEUE_JOB_TYPES = frozenset(
    {
        "refresh_leaderboard",
        "match_finished",
        "cleanup_rooms",
    }
)

_SAFE_JOB_TYPE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_SENSITIVE_WORDS = (
    "authorization",
    "connection",
    "key",
    "password",
    "sas",
    "secret",
    "signature",
    "token",
)


@dataclass(frozen=True)
class QueueJobResult:
    ok: bool
    status: str
    job_type: str | None
    elapsed_ms: int
    backend_result: dict[str, Any] | None = None
    error: str | None = None


def decode_queue_job_message(
    raw_message: bytes | str,
) -> tuple[dict[str, Any] | None, str | None]:
    text = (
        raw_message.decode("utf-8", errors="replace")
        if isinstance(raw_message, bytes)
        else str(raw_message)
    ).strip()

    for candidate in (text, _try_base64_decode(text)):
        if not candidate:
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload, None
        return None, "queue message JSON must be an object"

    return None, "queue message body is not valid JSON"


def normalize_queue_job_type(payload: Mapping[str, Any]) -> str | None:
    value = payload.get("type")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower()


def safe_job_type_for_log(job_type: Any) -> str:
    value = "" if job_type is None else str(job_type).strip()
    lowered = value.lower()
    if not value:
        return "<missing>"
    if any(word in lowered for word in _SENSITIVE_WORDS):
        return "<redacted>"
    if not _SAFE_JOB_TYPE_RE.fullmatch(value):
        return "<redacted>"
    return value


def process_queue_job_message(
    raw_message: bytes | str,
    handler: Callable[[str, Mapping[str, Any]], Mapping[str, Any] | None],
    clock: Callable[[], float] = time.perf_counter,
) -> QueueJobResult:
    started_at = clock()
    payload, error = decode_queue_job_message(raw_message)
    if error:
        return QueueJobResult(
            ok=False,
            status="invalid_json",
            job_type=None,
            elapsed_ms=_elapsed_ms(started_at, clock),
            error=error,
        )

    job_type = normalize_queue_job_type(payload)
    if job_type not in SUPPORTED_QUEUE_JOB_TYPES:
        return QueueJobResult(
            ok=False,
            status="unsupported_type",
            job_type=job_type,
            elapsed_ms=_elapsed_ms(started_at, clock),
            error="unsupported job type",
        )

    try:
        backend_result = dict(handler(job_type, payload) or {})
    except Exception as exc:
        return QueueJobResult(
            ok=False,
            status="handler_exception",
            job_type=job_type,
            elapsed_ms=_elapsed_ms(started_at, clock),
            error=type(exc).__name__,
        )

    ok = bool(backend_result.get("ok", True))
    return QueueJobResult(
        ok=ok,
        status="processed" if ok else "backend_failed",
        job_type=job_type,
        elapsed_ms=_elapsed_ms(started_at, clock),
        backend_result=backend_result,
    )


def _try_base64_decode(text: str) -> str | None:
    try:
        return base64.b64decode(text, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _elapsed_ms(started_at: float, clock: Callable[[], float]) -> int:
    return round((clock() - started_at) * 1000)
