import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-room-api-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from server.database import engine, init_db
from server.main import app
from server.models import Match, Room, RoomPlayer


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


def create_room_with_guest(prefix):
    host_token = create_user_and_token(f"{prefix}_host")
    guest_token = create_user_and_token(f"{prefix}_guest")
    room = client.post("/rooms", json={"mode": "1v1"}, headers=auth(host_token)).json()
    joined = client.post(
        f"/rooms/{room['room_code']}/join", headers=auth(guest_token)
    ).json()
    return room["room_code"], joined, host_token, guest_token


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


def test_guest_leaves_first_then_host_can_leave_and_room_is_removed():
    room_code, _, host_token, guest_token = create_room_with_guest("guest_first")

    guest_leave = client.post(f"/rooms/{room_code}/leave", headers=auth(guest_token))
    assert guest_leave.status_code == 200
    refreshed = client.get(f"/rooms/{room_code}", headers=auth(host_token))
    assert refreshed.status_code == 200
    assert len(refreshed.json()["players"]) == 1

    host_leave = client.post(f"/rooms/{room_code}/leave", headers=auth(host_token))
    assert host_leave.status_code == 200
    assert client.get(f"/rooms/{room_code}", headers=auth(host_token)).status_code == 404


def test_host_leaves_first_guest_becomes_host_then_can_leave():
    room_code, joined, host_token, guest_token = create_room_with_guest("host_first")
    guest_id = next(
        player["user_id"]
        for player in joined["players"]
        if player["username"] == "host_first_guest"
    )

    host_leave = client.post(f"/rooms/{room_code}/leave", headers=auth(host_token))
    assert host_leave.status_code == 200
    refreshed = client.get(f"/rooms/{room_code}", headers=auth(guest_token))
    assert refreshed.status_code == 200
    assert refreshed.json()["host_user_id"] == guest_id
    assert refreshed.json()["players"][0]["is_host"] is True

    guest_leave = client.post(f"/rooms/{room_code}/leave", headers=auth(guest_token))
    assert guest_leave.status_code == 200
    assert client.get(f"/rooms/{room_code}", headers=auth(guest_token)).status_code == 404


def test_leave_room_twice_is_idempotent():
    token = create_user_and_token("leave_twice_host")
    room = client.post("/rooms", json={"mode": "1v1"}, headers=auth(token)).json()
    path = f"/rooms/{room['room_code']}/leave"

    first = client.post(path, headers=auth(token))
    second = client.post(path, headers=auth(token))

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"success": True}
    assert second.json() == {"success": True}


def test_two_players_leave_near_simultaneously():
    room_code, _, host_token, guest_token = create_room_with_guest("leave_race")
    path = f"/rooms/{room_code}/leave"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda token: client.post(path, headers=auth(token)).status_code,
                [host_token, guest_token],
            )
        )

    assert results == [200, 200]
    with Session(engine) as session:
        room = session.exec(
            select(Room).where(Room.room_code == room_code)
        ).first()
        if room:
            players = session.exec(
                select(RoomPlayer).where(RoomPlayer.room_id == room.id)
            ).all()
            assert players == []


def test_leave_room_with_active_match_cancels_match_and_remaining_player_can_leave():
    room_code, _, host_token, guest_token = create_room_with_guest("active_leave")
    ready = client.post(f"/rooms/{room_code}/ready", headers=auth(guest_token))
    assert ready.status_code == 200
    match = client.post(f"/rooms/{room_code}/start", headers=auth(host_token)).json()
    match_id = match["match_id"]

    host_leave = client.post(f"/rooms/{room_code}/leave", headers=auth(host_token))
    assert host_leave.status_code == 200
    refreshed = client.get(f"/rooms/{room_code}", headers=auth(guest_token))
    assert refreshed.status_code == 200
    data = refreshed.json()
    assert data["status"] == "waiting"
    assert len(data["players"]) == 1
    assert data["players"][0]["username"] == "active_leave_guest"
    assert data["players"][0]["is_host"] is True
    assert data["players"][0]["is_ready"] is False
    active_match = client.get(
        f"/rooms/{room_code}/active-match", headers=auth(guest_token)
    )
    assert active_match.status_code == 404
    with Session(engine) as session:
        cancelled_match = session.get(Match, match_id)
        assert cancelled_match.status == "cancelled"

    guest_leave = client.post(f"/rooms/{room_code}/leave", headers=auth(guest_token))
    assert guest_leave.status_code == 200
    assert client.get(f"/rooms/{room_code}", headers=auth(guest_token)).status_code == 404
