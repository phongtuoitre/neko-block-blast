import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-match-api-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")

from fastapi.testclient import TestClient
from sqlmodel import Session

from server.database import engine, init_db
from server.main import app
from server.models import Match


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


def prepare_1v1(prefix, ready_guest=True):
    host_token = create_user_and_token(f"{prefix}_host")
    guest_token = create_user_and_token(f"{prefix}_guest")
    room = client.post(
        "/rooms", json={"mode": "1v1"}, headers=auth(host_token)
    ).json()
    code = room["room_code"]
    client.post(f"/rooms/{code}/join", headers=auth(guest_token))
    if ready_guest:
        client.post(f"/rooms/{code}/ready", headers=auth(guest_token))
    return code, host_token, guest_token


def test_host_starts_1v1_successfully():
    code, host_token, _ = prepare_1v1("start_ok")
    response = client.post(f"/rooms/{code}/start", headers=auth(host_token))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "playing"
    assert data["mode"] == "1v1"
    assert len(data["players"]) == 2


def test_non_host_cannot_start():
    code, _, guest_token = prepare_1v1("non_host")
    response = client.post(f"/rooms/{code}/start", headers=auth(guest_token))
    assert response.status_code == 403


def test_room_requires_two_players_to_start():
    host_token = create_user_and_token("solo_match_host")
    room = client.post(
        "/rooms", json={"mode": "1v1"}, headers=auth(host_token)
    ).json()
    response = client.post(
        f"/rooms/{room['room_code']}/start", headers=auth(host_token)
    )
    assert response.status_code == 409
    assert "exactly 2" in response.json()["detail"]


def test_player_submits_score_successfully():
    code, host_token, _ = prepare_1v1("score_ok")
    match = client.post(f"/rooms/{code}/start", headers=auth(host_token)).json()
    response = client.post(
        f"/matches/{match['match_id']}/score",
        json={"score": 1230},
        headers=auth(host_token),
    )
    assert response.status_code == 200
    host = next(
        player
        for player in response.json()["players"]
        if player["username"] == "score_ok_host"
    )
    assert host["score"] == 1230


def test_score_cannot_decrease():
    code, host_token, _ = prepare_1v1("score_down")
    match = client.post(f"/rooms/{code}/start", headers=auth(host_token)).json()
    path = f"/matches/{match['match_id']}/score"
    client.post(path, json={"score": 500}, headers=auth(host_token))
    response = client.post(path, json={"score": 400}, headers=auth(host_token))
    assert response.status_code == 409
    assert response.json()["detail"] == "Score cannot decrease"


def test_get_match_returns_remaining_seconds():
    code, host_token, _ = prepare_1v1("remaining")
    match = client.post(f"/rooms/{code}/start", headers=auth(host_token)).json()
    response = client.get(
        f"/matches/{match['match_id']}", headers=auth(host_token)
    )
    assert response.status_code == 200
    assert 0 <= response.json()["remaining_seconds"] <= 120


def test_get_match_finalizes_expired_match():
    code, host_token, guest_token = prepare_1v1("finalize")
    match_data = client.post(
        f"/rooms/{code}/start", headers=auth(host_token)
    ).json()
    match_id = match_data["match_id"]
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 900},
        headers=auth(host_token),
    )
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 300},
        headers=auth(guest_token),
    )
    with Session(engine) as session:
        match = session.get(Match, match_id)
        match.ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(match)
        session.commit()

    response = client.get(f"/matches/{match_id}", headers=auth(host_token))
    data = response.json()
    assert response.status_code == 200
    assert data["status"] == "finished"
    assert data["remaining_seconds"] == 0
    results = {player["username"]: player["result"] for player in data["players"]}
    assert results["finalize_host"] == "win"
    assert results["finalize_guest"] == "lose"
