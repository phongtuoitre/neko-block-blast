import base64

from azure_functions.neko_monitor.queue_jobs import (
    decode_queue_job_message,
    process_queue_job_message,
    safe_job_type_for_log,
)


def test_decode_plain_json_queue_message():
    payload, error = decode_queue_job_message(b'{"type":"refresh_leaderboard"}')

    assert error is None
    assert payload["type"] == "refresh_leaderboard"


def test_decode_base64_json_queue_message():
    raw = base64.b64encode(b'{"type":"cleanup_rooms"}')
    payload, error = decode_queue_job_message(raw)

    assert error is None
    assert payload["type"] == "cleanup_rooms"


def test_invalid_json_does_not_call_handler():
    called = False

    def handler(job_type, payload):
        nonlocal called
        called = True

    result = process_queue_job_message("not-json-secret-token", handler)

    assert result.status == "invalid_json"
    assert called is False
    assert "not-json-secret-token" not in (result.error or "")


def test_unsupported_type_does_not_call_handler():
    called = False

    def handler(job_type, payload):
        nonlocal called
        called = True

    result = process_queue_job_message('{"type":"unknown"}', handler)

    assert result.status == "unsupported_type"
    assert result.job_type == "unknown"
    assert called is False


def test_supported_message_calls_handler_without_storing_payload_secret():
    calls = []

    def handler(job_type, payload):
        calls.append((job_type, payload["room_id"]))
        return {"ok": True, "status_code": 200, "latency_ms": 7}

    result = process_queue_job_message(
        '{"type":"cleanup_rooms","room_id":"R1","token":"secret"}',
        handler,
    )

    assert result.ok is True
    assert result.status == "processed"
    assert calls == [("cleanup_rooms", "R1")]
    assert "secret" not in repr(result)


def test_safe_job_type_redacts_suspicious_values():
    assert safe_job_type_for_log("refresh_leaderboard") == "refresh_leaderboard"
    assert safe_job_type_for_log("token=abc123") == "<redacted>"
