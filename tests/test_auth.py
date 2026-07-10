import os
import tempfile
from pathlib import Path


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-api-test-"))
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = f"sqlite:///{test_db_dir / 'test.db'}"

from fastapi.testclient import TestClient  # noqa: E402

from server.database import init_db  # noqa: E402
from server.main import app  # noqa: E402


client = TestClient(app)


def setup_module():
    init_db()


def register_user(username="phong", email="phong@gmail.com", password="12345678"):
    return client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": "Phong",
            "email": email,
            "password": password,
        },
    )


def login_user(username="phong", password="12345678"):
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "neko-block-blast-api"}


def test_register_success():
    response = register_user(username="register_ok", email="register-ok@gmail.com")
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "register_ok"
    assert data["email"] == "register-ok@gmail.com"
    assert "password_hash" not in data


def test_duplicate_username_rejected_case_insensitive():
    first = register_user(username="dupe_name", email="dupe1@gmail.com")
    second = register_user(username="DUPE_NAME", email="dupe2@gmail.com")
    assert first.status_code == 201
    assert second.status_code == 409


def test_login_success():
    register_user(username="login_ok", email="login-ok@gmail.com")
    response = login_user(username="login_ok")
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_login_wrong_password():
    register_user(username="wrong_pass", email="wrong-pass@gmail.com")
    response = login_user(username="wrong_pass", password="bad-password")
    assert response.status_code == 401


def test_me_with_valid_token():
    register_user(username="me_user", email="me-user@gmail.com")
    login_response = login_user(username="me_user")
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "me_user"


def test_forgot_password_rejects_non_gmail():
    response = client.post(
        "/auth/forgot-password",
        json={"email": "user@example.com"},
    )
    assert response.status_code == 422


def test_forgot_password_accepts_registered_gmail(monkeypatch):
    register_user(username="forgot_ok", email="forgot-ok@gmail.com")
    sent = {}

    def capture_email(email, code):
        sent["email"] = email
        sent["code"] = code

    monkeypatch.setattr("server.routers.auth.send_password_reset_email", capture_email)
    response = client.post(
        "/auth/forgot-password",
        json={"email": "forgot-ok@gmail.com"},
    )
    assert response.status_code == 200
    assert sent["email"] == "forgot-ok@gmail.com"
    assert len(sent["code"]) == 6
    assert sent["code"].isdigit()


def test_reset_password_rejects_wrong_code(monkeypatch):
    register_user(username="reset_wrong", email="reset-wrong@gmail.com")
    sent = {}
    monkeypatch.setattr(
        "server.routers.auth.send_password_reset_email",
        lambda email, code: sent.update(code=code),
    )
    client.post(
        "/auth/forgot-password",
        json={"email": "reset-wrong@gmail.com"},
    )
    wrong_code = "000000" if sent["code"] != "000000" else "111111"
    response = client.post(
        "/auth/reset-password",
        json={
            "email": "reset-wrong@gmail.com",
            "code": wrong_code,
            "new_password": "newpassword123",
        },
    )
    assert response.status_code == 400


def test_reset_password_success_and_login_with_new_password(monkeypatch):
    register_user(username="reset_ok", email="reset-ok@gmail.com")
    sent = {}
    monkeypatch.setattr(
        "server.routers.auth.send_password_reset_email",
        lambda email, code: sent.update(code=code),
    )
    client.post(
        "/auth/forgot-password",
        json={"email": "reset-ok@gmail.com"},
    )
    response = client.post(
        "/auth/reset-password",
        json={
            "email": "reset-ok@gmail.com",
            "code": sent["code"],
            "new_password": "newpassword123",
        },
    )
    assert response.status_code == 200

    old_login = login_user(username="reset_ok", password="12345678")
    new_login = login_user(username="reset_ok", password="newpassword123")
    assert old_login.status_code == 401
    assert new_login.status_code == 200
