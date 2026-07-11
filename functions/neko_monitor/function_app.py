import json
import logging
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import azure.functions as func


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

BACKEND_BASE_URL = "https://neko-block-api-nhom2-bwc3eyd3hvgucgdt.southeastasia-01.azurewebsites.net"


def call_json_api(path: str) -> dict:
    url = f"{BACKEND_BASE_URL}{path}"
    request = Request(url, headers={"User-Agent": "neko-monitor-function"})

    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


@app.route(route="neko-monitor", methods=["GET"])
def neko_monitor(req: func.HttpRequest) -> func.HttpResponse:
    checked_at = datetime.now(timezone.utc).isoformat()

    result = {
        "service": "neko-monitor-function",
        "purpose": "Serverless monitor for Neko Block Blast backend",
        "backend_base_url": BACKEND_BASE_URL,
        "checked_at": checked_at,
        "backend_health": None,
        "backend_version": None,
        "status": "unknown",
    }

    try:
        health = call_json_api("/health")
        result["backend_health"] = health

        try:
            version = call_json_api("/version")
            result["backend_version"] = version
        except Exception as version_error:
            result["backend_version"] = {
                "warning": "Could not read /version",
                "error": str(version_error),
            }

        result["status"] = "ok"

        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False, indent=2),
            status_code=200,
            mimetype="application/json",
        )

    except HTTPError as error:
        result["status"] = "backend_http_error"
        result["error"] = f"HTTP {error.code}: {error.reason}"

        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False, indent=2),
            status_code=502,
            mimetype="application/json",
        )

    except URLError as error:
        result["status"] = "backend_connection_error"
        result["error"] = str(error.reason)

        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False, indent=2),
            status_code=503,
            mimetype="application/json",
        )

    except Exception as error:
        result["status"] = "function_error"
        result["error"] = str(error)

        return func.HttpResponse(
            json.dumps(result, ensure_ascii=False, indent=2),
            status_code=500,
            mimetype="application/json",
        )


@app.timer_trigger(
    schedule="0 */15 * * * *",
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=True,
)
def scheduled_neko_monitor(mytimer: func.TimerRequest) -> None:
    try:
        health = call_json_api("/health")
        logging.info("Scheduled Neko backend health check OK: %s", health)
    except Exception as error:
        logging.error("Scheduled Neko backend health check FAILED: %s", error)
