import os
import tempfile
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-match-api-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")

from fastapi.testclient import TestClient
from sqlmodel import Session

from server.database import engine, init_db
from server import match_result_events
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


class ResourceExistsError(Exception):
    pass


class FakeBlobStorage:
    def __init__(self, fail_upload=False):
        self.fail_upload = fail_upload
        self.uploaded_paths = set()
        self.uploads = []
        self.container_name = None

    def get_container_client(self, container_name):
        self.container_name = container_name
        return self

    def get_blob_client(self, blob_path):
        return FakeBlobClient(self, blob_path)


class FakeBlobClient:
    def __init__(self, storage, blob_path):
        self.storage = storage
        self.blob_path = blob_path

    def upload_blob(self, data, overwrite=False, **kwargs):
        if self.storage.fail_upload:
            raise RuntimeError("temporary blob outage token=secret")
        if not overwrite and self.blob_path in self.storage.uploaded_paths:
            raise ResourceExistsError("blob already exists")
        self.storage.uploaded_paths.add(self.blob_path)
        self.storage.uploads.append(
            {
                "path": self.blob_path,
                "payload": json.loads(data.decode("utf-8")),
                "overwrite": overwrite,
                "options": kwargs,
            }
        )


def configure_fake_blob_storage(monkeypatch, storage):
    monkeypatch.setenv(
        "AZURE_STORAGE_ACCOUNT_URL",
        "https://nekoblockblastnhom2.blob.core.windows.net",
    )
    monkeypatch.setenv("MATCH_RESULTS_CONTAINER", "eventgrid-demo")
    monkeypatch.setattr(
        match_result_events,
        "create_blob_service_client",
        lambda account_url: storage,
    )
    monkeypatch.setattr(
        match_result_events,
        "create_json_content_settings",
        lambda: None,
    )


def expire_match(match_id):
    with Session(engine) as session:
        match = session.get(Match, match_id)
        now = datetime.now(timezone.utc)
        match.started_at = now - timedelta(seconds=121)
        match.ends_at = now - timedelta(seconds=1)
        session.add(match)
        session.commit()


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


def test_finished_match_uploads_match_result_json(monkeypatch):
    storage = FakeBlobStorage()
    configure_fake_blob_storage(monkeypatch, storage)
    code, host_token, guest_token = prepare_1v1("blob_success")
    match_data = client.post(
        f"/rooms/{code}/start", headers=auth(host_token)
    ).json()
    match_id = match_data["match_id"]
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 1400},
        headers=auth(host_token),
    )
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 500},
        headers=auth(guest_token),
    )
    expire_match(match_id)

    response = client.get(f"/matches/{match_id}", headers=auth(host_token))
    data = response.json()

    assert response.status_code == 200
    assert data["status"] == "finished"
    assert data["event_blob_uploaded"] is True
    assert data["event_blob_path"].startswith("match-results/")
    assert data["event_blob_path"].endswith(f"/{match_id}.json")
    assert storage.container_name == "eventgrid-demo"
    assert len(storage.uploads) == 1
    upload = storage.uploads[0]
    assert upload["path"] == data["event_blob_path"]
    assert upload["overwrite"] is False
    payload = upload["payload"]
    assert payload["match_id"] == match_id
    assert payload["room_id"] > 0
    assert payload["room_code"] == code
    assert payload["status"] == "finished"
    assert payload["duration_seconds"] == 120
    assert payload["completed_at"]
    players = {player["username"]: player for player in payload["players"]}
    assert players["blob_success_host"]["score"] == 1400
    assert players["blob_success_host"]["result"] == "win"
    assert players["blob_success_guest"]["score"] == 500
    assert players["blob_success_guest"]["result"] == "lose"


def test_blob_upload_error_keeps_finished_match_in_database(monkeypatch, caplog):
    storage = FakeBlobStorage(fail_upload=True)
    configure_fake_blob_storage(monkeypatch, storage)
    code, host_token, guest_token = prepare_1v1("blob_error")
    match_data = client.post(
        f"/rooms/{code}/start", headers=auth(host_token)
    ).json()
    match_id = match_data["match_id"]
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 1000},
        headers=auth(host_token),
    )
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 900},
        headers=auth(guest_token),
    )
    expire_match(match_id)

    with caplog.at_level(logging.WARNING):
        response = client.get(f"/matches/{match_id}", headers=auth(host_token))

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "finished"
    assert data["event_blob_uploaded"] is False
    assert data["event_blob_path"].endswith(f"/{match_id}.json")
    assert "Neko match result blob upload failed" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "secret" not in caplog.text
    with Session(engine) as session:
        match = session.get(Match, match_id)
        assert match.status == "finished"
        assert match.winner_user_id is not None


def test_repeated_finished_match_request_does_not_create_duplicate_blob(monkeypatch):
    storage = FakeBlobStorage()
    configure_fake_blob_storage(monkeypatch, storage)
    code, host_token, guest_token = prepare_1v1("blob_repeat")
    match_data = client.post(
        f"/rooms/{code}/start", headers=auth(host_token)
    ).json()
    match_id = match_data["match_id"]
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 700},
        headers=auth(host_token),
    )
    client.post(
        f"/matches/{match_id}/score",
        json={"score": 650},
        headers=auth(guest_token),
    )
    expire_match(match_id)

    first_response = client.get(f"/matches/{match_id}", headers=auth(host_token))
    second_response = client.get(f"/matches/{match_id}", headers=auth(host_token))

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["event_blob_uploaded"] is True
    assert second_response.json()["event_blob_uploaded"] is True
    assert first_response.json()["event_blob_path"] == second_response.json()[
        "event_blob_path"
    ]
    assert len(storage.uploads) == 1
