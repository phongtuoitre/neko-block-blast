import json
import os
import urllib.error
import urllib.parse
import urllib.request


API_BASE_URL = os.getenv(
    "NEKO_API_BASE_URL",
    "https://apim-neko-game-nhom2-2026.azure-api.net/neko",
).rstrip("/")
TIMEOUT_SECONDS = 5


class ApiError(Exception):
    def __init__(self, kind, detail="", status_code=None, response_body=""):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.status_code = status_code
        self.response_body = response_body


def _request(path, method="GET", data=None, headers=None):
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        data=data,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw_body = response.read().decode("utf-8")
            if not raw_body:
                return {}
            return json.loads(raw_body)
    except urllib.error.HTTPError as exc:
        response_body = ""
        try:
            response_body = exc.read().decode("utf-8", errors="replace")
            payload = json.loads(response_body)
            detail = payload.get("detail", "")
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = ""
        raise ApiError("http", str(detail), exc.code, response_body) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError("connection", type(exc).__name__) from exc


def login(username, password):
    body = urllib.parse.urlencode(
        {"username": username, "password": password}
    ).encode("utf-8")
    return _request(
        "/auth/login",
        method="POST",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def register(username, display_name, email, password):
    body = json.dumps(
        {
            "username": username,
            "display_name": display_name,
            "email": email,
            "password": password,
        }
    ).encode("utf-8")
    return _request(
        "/auth/register",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )


def get_current_user(access_token):
    return _request(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )


def forgot_password(email):
    body = json.dumps({"email": email}).encode("utf-8")
    return _request(
        "/auth/forgot-password",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )


def reset_password(email, code, new_password):
    body = json.dumps(
        {
            "email": email,
            "code": code,
            "new_password": new_password,
        }
    ).encode("utf-8")
    return _request(
        "/auth/reset-password",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )


def _bearer_headers(access_token, include_json=False):
    headers = {"Authorization": f"Bearer {access_token}"}
    if include_json:
        headers["Content-Type"] = "application/json"
    return headers


def create_room(access_token, mode):
    body = json.dumps({"mode": mode}).encode("utf-8")
    return _request(
        "/rooms",
        method="POST",
        data=body,
        headers=_bearer_headers(access_token, include_json=True),
    )


def join_room(access_token, room_code):
    code = urllib.parse.quote(room_code.strip().upper())
    return _request(
        f"/rooms/{code}/join",
        method="POST",
        data=b"",
        headers=_bearer_headers(access_token),
    )


def get_room(access_token, room_code):
    code = urllib.parse.quote(room_code.strip().upper())
    return _request(
        f"/rooms/{code}",
        headers=_bearer_headers(access_token),
    )


def leave_room(access_token, room_code):
    code = urllib.parse.quote(room_code.strip().upper())
    return _request(
        f"/rooms/{code}/leave",
        method="POST",
        data=b"",
        headers=_bearer_headers(access_token),
    )


def toggle_ready(access_token, room_code):
    code = urllib.parse.quote(room_code.strip().upper())
    return _request(
        f"/rooms/{code}/ready",
        method="POST",
        data=b"",
        headers=_bearer_headers(access_token),
    )


def start_room(access_token, room_code):
    code = urllib.parse.quote(room_code.strip().upper())
    return _request(
        f"/rooms/{code}/start",
        method="POST",
        data=b"",
        headers=_bearer_headers(access_token),
    )


def get_active_match(access_token, room_code):
    code = urllib.parse.quote(room_code.strip().upper())
    return _request(
        f"/rooms/{code}/active-match",
        headers=_bearer_headers(access_token),
    )


def get_match(access_token, match_id):
    return _request(
        f"/matches/{int(match_id)}",
        headers=_bearer_headers(access_token),
    )


def submit_score(access_token, match_id, score):
    body = json.dumps({"score": int(score)}).encode("utf-8")
    return _request(
        f"/matches/{int(match_id)}/score",
        method="POST",
        data=body,
        headers=_bearer_headers(access_token, include_json=True),
    )
