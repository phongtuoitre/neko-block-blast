import json
import logging
import os
import time
import urllib.error
import urllib.request

import azure.functions as func


app = func.FunctionApp()

BACKEND_TIMEOUT_SECONDS = 10


def _backend_base_url() -> str:
    return os.environ.get("NEKO_API_BASE_URL", "").strip().rstrip("/")


def _job_key() -> str:
    return os.environ.get("NEKO_JOB_KEY", "").strip()


def _json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _parse_json_response(raw_body: bytes):
    if not raw_body:
        return None
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw_body.decode("utf-8", errors="replace")


def _call_backend(path: str, method: str = "GET", include_job_key: bool = False) -> dict:
    backend_url = _backend_base_url()
    if not backend_url:
        return {
            "ok": False,
            "backend_url": "",
            "status_code": None,
            "latency_ms": None,
            "data": None,
            "message": "NEKO_API_BASE_URL is not configured",
        }

    headers = {
        "Accept": "application/json",
        "User-Agent": "neko-monitor-function",
    }
    if include_job_key:
        job_key = _job_key()
        if not job_key:
            return {
                "ok": False,
                "backend_url": backend_url,
                "status_code": None,
                "latency_ms": None,
                "data": None,
                "message": "NEKO_JOB_KEY is not configured",
            }
        headers["X-Job-Key"] = job_key

    request_url = f"{backend_url}{path}"
    request_data = b"" if method.upper() in {"POST", "PUT", "PATCH"} else None
    request = urllib.request.Request(
        request_url,
        data=request_data,
        headers=headers,
        method=method.upper(),
    )
    started_at = time.perf_counter()

    try:
        with urllib.request.urlopen(request, timeout=BACKEND_TIMEOUT_SECONDS) as response:
            raw_body = response.read(1024 * 1024)
            status_code = response.getcode()
    except urllib.error.HTTPError as exc:
        raw_body = exc.read(1024 * 1024)
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": exc.code,
            "latency_ms": latency_ms,
            "data": _parse_json_response(raw_body),
            "message": f"Backend returned HTTP {exc.code}",
        }
    except urllib.error.URLError as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": None,
            "latency_ms": latency_ms,
            "data": None,
            "message": f"Backend request failed: {exc.reason}",
        }
    except TimeoutError:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": None,
            "latency_ms": latency_ms,
            "data": None,
            "message": "Backend request timed out",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        logging.exception("Unexpected backend request error")
        return {
            "ok": False,
            "backend_url": backend_url,
            "status_code": None,
            "latency_ms": latency_ms,
            "data": None,
            "message": f"Unexpected backend request error: {exc}",
        }

    latency_ms = round((time.perf_counter() - started_at) * 1000)
    return {
        "ok": 200 <= status_code < 300,
        "backend_url": backend_url,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "data": _parse_json_response(raw_body),
        "message": "Backend request OK"
        if 200 <= status_code < 300
        else f"Backend returned HTTP {status_code}",
    }


def _check_backend_health() -> dict:
    result = _call_backend("/health")
    return {
        "backend_url": result["backend_url"],
        "backend_ok": result["ok"],
        "status_code": result["status_code"],
        "latency_ms": result["latency_ms"],
        "message": "Backend is healthy" if result["ok"] else result["message"],
    }


def _proxy_backend_job(path: str, method: str = "GET") -> func.HttpResponse:
    result = _call_backend(path, method=method, include_job_key=True)
    if result["ok"] and isinstance(result["data"], dict):
        return _json_response(result["data"], status_code=result["status_code"] or 200)

    payload = {
        "backend_url": result["backend_url"],
        "backend_ok": result["ok"],
        "status_code": result["status_code"],
        "latency_ms": result["latency_ms"],
        "message": result["message"],
    }
    if result["data"] is not None:
        payload["backend_response"] = result["data"]
    return _json_response(payload, status_code=result["status_code"] or 500)


@app.route(route="monitor/health-check", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def manual_health_check(req: func.HttpRequest) -> func.HttpResponse:
    result = {
        "function": "manual_health_check",
        **_check_backend_health(),
    }
    return _json_response(result)


@app.route(route="jobs/summary", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def jobs_summary(req: func.HttpRequest) -> func.HttpResponse:
    return _proxy_backend_job("/jobs/summary")


@app.route(
    route="jobs/cleanup-expired-rooms",
    methods=["POST"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def jobs_cleanup_expired_rooms(req: func.HttpRequest) -> func.HttpResponse:
    return _proxy_backend_job("/jobs/cleanup-expired-rooms", method="POST")


@app.route(
    route="jobs/leaderboard-online",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def jobs_leaderboard_online(req: func.HttpRequest) -> func.HttpResponse:
    return _proxy_backend_job("/jobs/leaderboard-online")


@app.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def health_monitor_timer(timer: func.TimerRequest) -> None:
    result = _check_backend_health()
    if result["backend_ok"]:
        logging.info(
            "Backend health OK url=%s status_code=%s latency_ms=%s",
            result["backend_url"],
            result["status_code"],
            result["latency_ms"],
        )
        return

    logging.warning(
        "Backend health FAILED url=%s status_code=%s latency_ms=%s message=%s",
        result["backend_url"],
        result["status_code"],
        result["latency_ms"],
        result["message"],
    )


@app.timer_trigger(
    schedule="0 */5 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def room_cleanup_timer(timer: func.TimerRequest) -> None:
    result = _call_backend(
        "/jobs/cleanup-expired-rooms",
        method="POST",
        include_job_key=True,
    )
    if result["ok"]:
        logging.info(
            "Expired room cleanup OK status_code=%s latency_ms=%s response=%s",
            result["status_code"],
            result["latency_ms"],
            result["data"],
        )
        return

    logging.warning(
        "Expired room cleanup FAILED status_code=%s latency_ms=%s message=%s response=%s",
        result["status_code"],
        result["latency_ms"],
        result["message"],
        result["data"],
    )


@app.timer_trigger(
    schedule="0 */30 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def game_stats_timer(timer: func.TimerRequest) -> None:
    result = _call_backend("/jobs/summary", include_job_key=True)
    if result["ok"] and isinstance(result["data"], dict):
        stats = result["data"]
        logging.info(
            "Game stats OK users=%s rooms=%s matches=%s playing_matches=%s",
            stats.get("total_users"),
            stats.get("total_rooms"),
            stats.get("total_matches"),
            stats.get("playing_matches"),
        )
        return

    logging.warning(
        "Game stats FAILED status_code=%s latency_ms=%s message=%s response=%s",
        result["status_code"],
        result["latency_ms"],
        result["message"],
        result["data"],
    )
