import os
import tempfile
from pathlib import Path


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-room-api-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")

from fastapi.testclient import TestClient

from server.database import init_db
from server.main import app


client = TestClient(app)


def setup_module():
    init_db()


def create_user_and_token(username):
    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "display_name": username.title(),
            "email": f"{username}@gmail.com",
            "password": "12345678",
        },
    )
    assert response.status_code == 201
    login_response = client.post(
        "/auth/login",
        data={"username": username, "password": "12345678"},
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_create_1v1_room_success():
    token = create_user_and_token("room_host_1")
    response = client.post("/rooms", json={"mode": "1v1"}, headers=auth(token))
    assert response.status_code == 201
    data = response.json()
    assert len(data["room_code"]) == 6
    assert data["mode"] == "1v1"
    assert data["players"][0]["team"] == 1
    assert data["players"][0]["is_host"] is True


def test_join_room_success():
    host_token = create_user_and_token("join_host")
    guest_token = create_user_and_token("join_guest")
    room = client.post("/rooms", json={"mode": "1v1"}, headers=auth(host_token)).json()
    response = client.post(
        f"/rooms/{room['room_code']}/join", headers=auth(guest_token)
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["players"]) == 2
    assert {player["team"] for player in data["players"]} == {1, 2}


def test_1v1_room_rejects_third_player():
    host_token = create_user_and_token("full_host")
    guest_token = create_user_and_token("full_guest")
    third_token = create_user_and_token("full_third")
    room = client.post("/rooms", json={"mode": "1v1"}, headers=auth(host_token)).json()
    client.post(f"/rooms/{room['room_code']}/join", headers=auth(guest_token))
    response = client.post(
        f"/rooms/{room['room_code']}/join", headers=auth(third_token)
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Room is full"


def test_create_2v2_room_success():
    token = create_user_and_token("room_host_2")
    response = client.post("/rooms", json={"mode": "2v2"}, headers=auth(token))
    assert response.status_code == 201
    assert response.json()["mode"] == "2v2"


def test_ready_toggle_success():
    token = create_user_and_token("ready_host")
    room = client.post("/rooms", json={"mode": "1v1"}, headers=auth(token)).json()
    response = client.post(
        f"/rooms/{room['room_code']}/ready", headers=auth(token)
    )
    assert response.status_code == 200
    assert response.json()["players"][0]["is_ready"] is True


def test_leave_room_success_and_transfers_host():
    host_token = create_user_and_token("leave_host")
    guest_token = create_user_and_token("leave_guest")
    room = client.post("/rooms", json={"mode": "1v1"}, headers=auth(host_token)).json()
    joined = client.post(
        f"/rooms/{room['room_code']}/join", headers=auth(guest_token)
    ).json()
    guest_id = next(
        player["user_id"]
        for player in joined["players"]
        if player["username"] == "leave_guest"
    )

    response = client.post(
        f"/rooms/{room['room_code']}/leave", headers=auth(host_token)
    )
    assert response.status_code == 200
    assert response.json() == {"success": True}
    refreshed = client.get(
        f"/rooms/{room['room_code']}", headers=auth(guest_token)
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["host_user_id"] == guest_id
