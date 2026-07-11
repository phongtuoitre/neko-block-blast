import os
import tempfile
from datetime import timedelta
from pathlib import Path


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-jobs-api-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")
os.environ.setdefault("ADMIN_JOB_KEY", "test-job-key")

from fastapi.testclient import TestClient
from sqlmodel import Session

from server.database import engine, init_db
from server.main import app
from server.models import Match, MatchPlayer, Room, RoomPlayer, User
from server.routers.matches import utc_now


client = TestClient(app)


def setup_module():
    init_db()


def job_headers(key="test-job-key"):
    return {"X-Job-Key": key}


def create_user(username):
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
    return response.json()


def test_jobs_summary_accepts_valid_key():
    response = client.get("/jobs/summary", headers=job_headers())
    assert response.status_code == 200
    data = response.json()
    assert {
        "total_users",
        "total_rooms",
        "waiting_rooms",
        "playing_rooms",
        "finished_rooms",
        "total_matches",
        "playing_matches",
        "finished_matches",
        "total_match_players",
    }.issubset(data)


def test_jobs_summary_rejects_invalid_key():
    response = client.get("/jobs/summary", headers=job_headers("wrong-key"))
    assert response.status_code == 403


def test_cleanup_expired_rooms_finishes_only_old_waiting_rooms():
    user = create_user("jobs_cleanup_host")
    with Session(engine) as session:
        old_room = Room(
            room_code="JCOLD1",
            mode="1v1",
            host_user_id=user["id"],
            status="waiting",
            created_at=utc_now() - timedelta(minutes=31),
        )
        fresh_room = Room(
            room_code="JCFRE1",
            mode="1v1",
            host_user_id=user["id"],
            status="waiting",
            created_at=utc_now(),
        )
        playing_room = Room(
            room_code="JCPLY1",
            mode="1v1",
            host_user_id=user["id"],
            status="playing",
            created_at=utc_now() - timedelta(minutes=60),
        )
        session.add(old_room)
        session.add(fresh_room)
        session.add(playing_room)
        session.commit()

    response = client.post("/jobs/cleanup-expired-rooms", headers=job_headers())
    assert response.status_code == 200
    assert response.json()["expired_rooms"] >= 1

    with Session(engine) as session:
        assert session.exec(select_room_status("JCOLD1")).one() == "finished"
        assert session.exec(select_room_status("JCFRE1")).one() == "waiting"
        assert session.exec(select_room_status("JCPLY1")).one() == "playing"


def select_room_status(room_code):
    from sqlmodel import select

    return select(Room.status).where(Room.room_code == room_code)


def test_online_leaderboard_returns_aggregated_rows():
    winner = create_user("jobs_lb_win")
    loser = create_user("jobs_lb_lose")
    now = utc_now()
    with Session(engine) as session:
        room = Room(
            room_code="JSLB01",
            mode="1v1",
            host_user_id=winner["id"],
            status="finished",
            created_at=now,
        )
        session.add(room)
        session.flush()
        session.add(RoomPlayer(room_id=room.id, user_id=winner["id"], team=1))
        session.add(RoomPlayer(room_id=room.id, user_id=loser["id"], team=2))
        match = Match(
            room_id=room.id,
            mode="1v1",
            status="finished",
            started_at=now - timedelta(minutes=3),
            ends_at=now - timedelta(minutes=1),
            winner_user_id=winner["id"],
            winner_team=1,
        )
        session.add(match)
        session.flush()
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=winner["id"],
                team=1,
                score=2000,
                result="win",
            )
        )
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=loser["id"],
                team=2,
                score=1200,
                result="lose",
            )
        )
        session.commit()

    response = client.get("/jobs/leaderboard-online", headers=job_headers())
    assert response.status_code == 200
    leaderboard = response.json()["leaderboard"]
    assert isinstance(leaderboard, list)
    winner_row = next(row for row in leaderboard if row["username"] == "jobs_lb_win")
    assert winner_row["wins"] >= 1
    assert winner_row["matches"] >= 1
    assert winner_row["total_score"] >= 2000


def test_ai_system_analysis_returns_source_without_azure_openai_config(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    response = client.get("/jobs/ai-system-analysis", headers=job_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["ai_enabled"] is False
    assert data["analysis"] == "Azure OpenAI is not configured."
    assert data["risk_level"] == "unknown"
    assert data["recommendations"] == []
    assert "summary" in data["source"]
    assert isinstance(data["source"]["leaderboard_count"], int)
