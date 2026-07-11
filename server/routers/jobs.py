import json
from datetime import timedelta
import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import case, func as sqlalchemy_func
from sqlmodel import Session, select

from server.config import get_admin_job_key, get_azure_openai_settings
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


def build_system_summary(session: Session) -> dict[str, int]:
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


def build_online_leaderboard(session: Session) -> list[dict[str, Any]]:
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
    return [
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


@router.get("/summary", dependencies=[Depends(require_job_key)])
def read_system_summary(session: Session = Depends(get_session)):
    return build_system_summary(session)


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
    return {
        "leaderboard": build_online_leaderboard(session)
    }


def build_ai_source(summary: dict[str, int], leaderboard: list[dict[str, Any]]):
    return {
        "summary": summary,
        "leaderboard_count": len(leaderboard),
    }


def azure_openai_is_configured(settings: dict[str, str]) -> bool:
    return all(
        [
            settings["endpoint"],
            settings["api_key"],
            settings["deployment"],
            settings["api_version"],
        ]
    )


def build_ai_prompt(summary: dict[str, int], leaderboard: list[dict[str, Any]]) -> str:
    source_data = json.dumps(
        {
            "summary": summary,
            "leaderboard": leaderboard,
        },
        ensure_ascii=False,
    )
    return (
        "Phân tích tình trạng vận hành hệ thống game Neko Block Blast bằng "
        "tiếng Việt. Hãy đánh giá backend, số user, số phòng, số trận, "
        "waiting rooms, leaderboard và đưa ra khuyến nghị vận hành.\n\n"
        f"Dữ liệu hiện tại:\n{source_data}\n\n"
        'Chỉ trả về JSON hợp lệ với dạng: {"analysis": "...", '
        '"risk_level": "low|medium|high", "recommendations": ["...", "..."]}.'
    )


def parse_ai_analysis(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {}

    analysis = str(parsed.get("analysis") or content or "").strip()
    if not analysis:
        analysis = "Azure OpenAI did not return an analysis."

    risk_level = str(parsed.get("risk_level") or "medium").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "medium"

    raw_recommendations = parsed.get("recommendations")
    recommendations = (
        [str(item) for item in raw_recommendations if item]
        if isinstance(raw_recommendations, list)
        else []
    )
    return {
        "analysis": analysis,
        "risk_level": risk_level,
        "recommendations": recommendations,
    }


@router.get("/ai-system-analysis", dependencies=[Depends(require_job_key)])
def read_ai_system_analysis(session: Session = Depends(get_session)):
    summary = build_system_summary(session)
    leaderboard = build_online_leaderboard(session)
    source = build_ai_source(summary, leaderboard)
    settings = get_azure_openai_settings()

    if not azure_openai_is_configured(settings):
        return {
            "ai_enabled": False,
            "analysis": "Azure OpenAI is not configured.",
            "risk_level": "unknown",
            "recommendations": [],
            "source": source,
        }

    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=settings["api_key"],
            azure_endpoint=settings["endpoint"],
            api_version=settings["api_version"],
        )
        completion = client.chat.completions.create(
            model=settings["deployment"],
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là chuyên gia vận hành hệ thống game online. "
                        "Luôn trả lời bằng JSON hợp lệ."
                    ),
                },
                {
                    "role": "user",
                    "content": build_ai_prompt(summary, leaderboard),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=700,
        )
        content = completion.choices[0].message.content or ""
        parsed = parse_ai_analysis(content)
        return {
            "ai_enabled": True,
            "analysis": parsed["analysis"],
            "risk_level": parsed["risk_level"],
            "recommendations": parsed["recommendations"],
            "source": source,
        }
    except Exception as exc:
        return {
            "ai_enabled": False,
            "analysis": f"Azure OpenAI request failed: {exc}",
            "risk_level": "unknown",
            "recommendations": [],
            "source": source,
        }
