from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine

from server.database import get_session
from server.main import app
from server.models import Match, MatchPlayer, Room, User


BASE_TIME = datetime(2026, 7, 30, 7, 0, tzinfo=timezone.utc)


@pytest.fixture()
def public_dashboard_client(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'public-dashboard.db'}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    def override_get_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app), engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def add_user(session, username, display_name):
    user = User(
        username=username,
        display_name=display_name,
        email=f"{username}@gmail.com",
        password_hash=f"hashed-password-for-{username}",
    )
    session.add(user)
    session.flush()
    return user


def add_match(
    session,
    *,
    room_code,
    players,
    status="finished",
    mode="1v1",
    winner=None,
    ends_offset_minutes=0,
):
    room = Room(
        room_code=room_code,
        mode=mode,
        host_user_id=players[0]["user"].id,
        status=status,
        created_at=BASE_TIME - timedelta(hours=1),
    )
    session.add(room)
    session.flush()
    match = Match(
        room_id=room.id,
        mode=mode,
        status=status,
        started_at=BASE_TIME + timedelta(minutes=ends_offset_minutes - 2),
        ends_at=BASE_TIME + timedelta(minutes=ends_offset_minutes),
        winner_user_id=winner.id if winner else None,
        winner_team=1 if winner else None,
    )
    session.add(match)
    session.flush()
    for index, player in enumerate(players, start=1):
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=player["user"].id,
                team=index,
                score=player["score"],
                result=player.get("result"),
            )
        )
    session.commit()
    return match.id


def test_public_dashboard_returns_200_without_token_on_empty_database(public_dashboard_client):
    client, _ = public_dashboard_client

    response = client.get("/public/dashboard")

    assert response.status_code == 200
    data = response.json()
    assert data["leaderboard"] == []
    assert data["recent_matches"] == []
    assert data["highlights"] == {
        "highest_score": {"display_name": None, "value": 0},
        "most_matches": {"display_name": None, "value": 0},
        "most_wins": {"display_name": None, "value": 0},
    }
    assert data["updated_at"]


def test_public_dashboard_does_not_expose_private_user_fields(public_dashboard_client):
    client, engine = public_dashboard_client
    with Session(engine) as session:
        user = add_user(session, "private_user", "Private Player")
        add_match(
            session,
            room_code="PUBL01",
            players=[{"user": user, "score": 900, "result": "win"}],
            winner=user,
        )

    response = client.get("/public/dashboard")
    body = json.dumps(response.json())

    assert response.status_code == 200
    assert "private_user@gmail.com" not in body
    assert "hashed-password-for-private_user" not in body
    assert "email" not in body
    assert "password" not in body
    assert "token" not in body


def test_public_dashboard_sorts_leaderboard_by_score_wins_then_matches(public_dashboard_client):
    client, engine = public_dashboard_client
    with Session(engine) as session:
        alpha = add_user(session, "alpha_sort", "Alpha")
        bravo = add_user(session, "bravo_sort", "Bravo")
        charlie = add_user(session, "charlie_sort", "Charlie")
        delta = add_user(session, "delta_sort", "Delta")

        add_match(
            session,
            room_code="SORT01",
            players=[{"user": delta, "score": 1200, "result": "lose"}],
        )
        add_match(
            session,
            room_code="SORT02",
            players=[{"user": charlie, "score": 400, "result": "win"}],
            winner=charlie,
        )
        add_match(
            session,
            room_code="SORT03",
            players=[{"user": charlie, "score": 300, "result": "win"}],
            winner=charlie,
        )
        add_match(
            session,
            room_code="SORT04",
            players=[{"user": charlie, "score": 300, "result": "lose"}],
        )
        add_match(
            session,
            room_code="SORT05",
            players=[{"user": bravo, "score": 500, "result": "win"}],
            winner=bravo,
        )
        add_match(
            session,
            room_code="SORT06",
            players=[{"user": bravo, "score": 500, "result": "win"}],
            winner=bravo,
        )
        add_match(
            session,
            room_code="SORT07",
            players=[{"user": alpha, "score": 800, "result": "win"}],
            winner=alpha,
        )
        add_match(
            session,
            room_code="SORT08",
            players=[{"user": alpha, "score": 200, "result": "lose"}],
        )

    response = client.get("/public/dashboard")
    leaderboard = response.json()["leaderboard"]

    assert response.status_code == 200
    assert [row["display_name"] for row in leaderboard] == [
        "Delta",
        "Charlie",
        "Bravo",
        "Alpha",
    ]
    assert [row["rank"] for row in leaderboard] == [1, 2, 3, 4]
    assert leaderboard[0]["total_score"] == 1200
    assert leaderboard[1]["wins"] == 2
    assert leaderboard[1]["matches"] == 3
    assert leaderboard[3]["best_score"] == 800


def test_public_dashboard_highlights_are_correct(public_dashboard_client):
    client, engine = public_dashboard_client
    with Session(engine) as session:
        highest = add_user(session, "highest_score", "Highest Score")
        most_matches = add_user(session, "most_matches", "Most Matches")
        most_wins = add_user(session, "most_wins", "Most Wins")

        add_match(
            session,
            room_code="HIGH01",
            players=[{"user": highest, "score": 5000, "result": "lose"}],
        )
        for index in range(4):
            add_match(
                session,
                room_code=f"MANY{index + 1:02d}",
                players=[
                    {
                        "user": most_matches,
                        "score": 100 + index,
                        "result": "win" if index == 0 else "lose",
                    }
                ],
                winner=most_matches if index == 0 else None,
            )
        for index in range(3):
            add_match(
                session,
                room_code=f"WINS{index + 1:02d}",
                players=[{"user": most_wins, "score": 200 + index, "result": "win"}],
                winner=most_wins,
            )

    response = client.get("/public/dashboard")
    highlights = response.json()["highlights"]

    assert response.status_code == 200
    assert highlights["highest_score"] == {"display_name": "Highest Score", "value": 5000}
    assert highlights["most_matches"] == {"display_name": "Most Matches", "value": 4}
    assert highlights["most_wins"] == {"display_name": "Most Wins", "value": 3}


def test_public_dashboard_recent_matches_only_contains_finished_matches(public_dashboard_client):
    client, engine = public_dashboard_client
    with Session(engine) as session:
        winner = add_user(session, "recent_winner", "Recent Winner")
        other = add_user(session, "recent_other", "Recent Other")
        older = add_match(
            session,
            room_code="REC001",
            players=[
                {"user": winner, "score": 1600, "result": "win"},
                {"user": other, "score": 900, "result": "lose"},
            ],
            winner=winner,
            ends_offset_minutes=1,
        )
        playing = add_match(
            session,
            room_code="REC002",
            players=[{"user": other, "score": 400, "result": None}],
            status="playing",
            ends_offset_minutes=3,
        )
        newest = add_match(
            session,
            room_code="REC003",
            players=[
                {"user": other, "score": 2200, "result": "win"},
                {"user": winner, "score": 2100, "result": "lose"},
            ],
            winner=other,
            ends_offset_minutes=5,
        )

    response = client.get("/public/dashboard")
    recent_matches = response.json()["recent_matches"]

    assert response.status_code == 200
    assert [row["match_id"] for row in recent_matches] == [newest, older]
    assert playing not in [row["match_id"] for row in recent_matches]
    assert recent_matches[0]["winner_display_name"] == "Recent Other"
    assert recent_matches[0]["top_score"] == 2200
    assert recent_matches[0]["finished_at"]
