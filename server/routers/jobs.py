from datetime import timedelta
import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import case, func as sqlalchemy_func
from sqlmodel import Session, select

from server.config import get_admin_job_key
from server.database import get_session
from server.models import Match, MatchPlayer, Room, User
from server.routers.matches import utc_now


router = APIRouter(prefix="/jobs", tags=["jobs"])


def require_job_key(x_job_key: str | None = Header(default=None)):
    expected_key = get_admin_job_key()
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_JOB_KEY is not configured",
        )
    if not x_job_key or not hmac.compare_digest(x_job_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid job key",
        )


def count_query(session: Session, column, *conditions) -> int:
    statement = select(sqlalchemy_func.count(column))
    for condition in conditions:
        statement = statement.where(condition)
    return session.exec(statement).one()


@router.get("/summary", dependencies=[Depends(require_job_key)])
def read_system_summary(session: Session = Depends(get_session)):
    return {
        "total_users": count_query(session, User.id),
        "total_rooms": count_query(session, Room.id),
        "waiting_rooms": count_query(session, Room.id, Room.status == "waiting"),
        "playing_rooms": count_query(session, Room.id, Room.status == "playing"),
        "finished_rooms": count_query(session, Room.id, Room.status == "finished"),
        "total_matches": count_query(session, Match.id),
        "playing_matches": count_query(session, Match.id, Match.status == "playing"),
        "finished_matches": count_query(session, Match.id, Match.status == "finished"),
        "total_match_players": count_query(session, MatchPlayer.id),
    }


@router.post("/cleanup-expired-rooms", dependencies=[Depends(require_job_key)])
def cleanup_expired_rooms(session: Session = Depends(get_session)):
    cutoff = utc_now() - timedelta(minutes=30)
    expired_rooms = session.exec(
        select(Room).where(
            Room.status == "waiting",
            Room.created_at <= cutoff,
        )
    ).all()
    for room in expired_rooms:
        room.status = "finished"
        session.add(room)
    session.commit()
    return {
        "cleanup": "ok",
        "expired_rooms": len(expired_rooms),
    }


@router.get("/leaderboard-online", dependencies=[Depends(require_job_key)])
def read_online_leaderboard(session: Session = Depends(get_session)):
    wins_expression = sqlalchemy_func.sum(
        case((MatchPlayer.result == "win", 1), else_=0)
    )
    matches_expression = sqlalchemy_func.count(MatchPlayer.id)
    score_expression = sqlalchemy_func.coalesce(sqlalchemy_func.sum(MatchPlayer.score), 0)
    rows = session.exec(
        select(
            User.id,
            User.username,
            User.display_name,
            wins_expression,
            matches_expression,
            score_expression,
        )
        .join(MatchPlayer, MatchPlayer.user_id == User.id)
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(Match.status == "finished")
        .group_by(User.id, User.username, User.display_name)
        .order_by(wins_expression.desc(), score_expression.desc(), matches_expression.desc())
        .limit(20)
    ).all()
    return {
        "leaderboard": [
            {
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "wins": int(wins or 0),
                "matches": int(matches or 0),
                "total_score": int(total_score or 0),
            }
            for user_id, username, display_name, wins, matches, total_score in rows
        ]
    }
