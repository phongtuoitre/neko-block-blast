from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func as sqlalchemy_func
from sqlmodel import Session, select

from server.database import get_session
from server.models import Match, MatchPlayer, User
from server.schemas import (
    PublicDashboardHighlight,
    PublicDashboardHighlights,
    PublicDashboardLeaderboardItem,
    PublicDashboardRead,
    PublicDashboardRecentMatch,
)


router = APIRouter(prefix="/public", tags=["public"])


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_player_stats_statement():
    matches_expression = sqlalchemy_func.count(MatchPlayer.id)
    wins_expression = sqlalchemy_func.sum(
        case((MatchPlayer.result == "win", 1), else_=0)
    )
    total_score_expression = sqlalchemy_func.coalesce(
        sqlalchemy_func.sum(MatchPlayer.score), 0
    )
    best_score_expression = sqlalchemy_func.coalesce(
        sqlalchemy_func.max(MatchPlayer.score), 0
    )
    statement = (
        select(
            User.id,
            User.username,
            User.display_name,
            matches_expression,
            wins_expression,
            total_score_expression,
            best_score_expression,
        )
        .join(MatchPlayer, MatchPlayer.user_id == User.id)
        .join(Match, Match.id == MatchPlayer.match_id)
        .where(Match.status == "finished")
        .group_by(User.id, User.username, User.display_name)
    )
    return (
        statement,
        matches_expression,
        wins_expression,
        total_score_expression,
        best_score_expression,
    )


def build_public_leaderboard(session: Session) -> list[PublicDashboardLeaderboardItem]:
    (
        statement,
        matches_expression,
        wins_expression,
        total_score_expression,
        best_score_expression,
    ) = build_player_stats_statement()
    rows = session.exec(
        statement.order_by(
            total_score_expression.desc(),
            wins_expression.desc(),
            matches_expression.desc(),
            User.id.asc(),
        ).limit(10)
    ).all()
    return [
        PublicDashboardLeaderboardItem(
            rank=index,
            user_id=int(user_id),
            username=username,
            display_name=display_name,
            matches=int(matches or 0),
            wins=int(wins or 0),
            total_score=int(total_score or 0),
            best_score=int(best_score or 0),
        )
        for index, (
            user_id,
            username,
            display_name,
            matches,
            wins,
            total_score,
            best_score,
        ) in enumerate(rows, start=1)
    ]


def fetch_player_highlight(session: Session, metric_name: str) -> PublicDashboardHighlight:
    (
        statement,
        matches_expression,
        wins_expression,
        total_score_expression,
        best_score_expression,
    ) = build_player_stats_statement()
    metric_expressions = {
        "highest_score": best_score_expression,
        "most_matches": matches_expression,
        "most_wins": wins_expression,
    }
    metric_expression = metric_expressions[metric_name]
    row = session.exec(
        statement.order_by(
            metric_expression.desc(),
            total_score_expression.desc(),
            wins_expression.desc(),
            matches_expression.desc(),
            User.id.asc(),
        ).limit(1)
    ).first()
    if not row:
        return PublicDashboardHighlight()

    value_indexes = {
        "highest_score": 6,
        "most_matches": 3,
        "most_wins": 4,
    }
    return PublicDashboardHighlight(
        display_name=row[2],
        value=int(row[value_indexes[metric_name]] or 0),
    )


def build_public_highlights(session: Session) -> PublicDashboardHighlights:
    return PublicDashboardHighlights(
        highest_score=fetch_player_highlight(session, "highest_score"),
        most_matches=fetch_player_highlight(session, "most_matches"),
        most_wins=fetch_player_highlight(session, "most_wins"),
    )


def build_public_recent_matches(session: Session) -> list[PublicDashboardRecentMatch]:
    matches = session.exec(
        select(Match)
        .where(Match.status == "finished")
        .order_by(Match.ends_at.desc(), Match.id.desc())
        .limit(10)
    ).all()
    if not matches:
        return []

    winner_ids = {
        match.winner_user_id for match in matches if match.winner_user_id is not None
    }
    winners = {}
    if winner_ids:
        winners = {
            user.id: user
            for user in session.exec(select(User).where(User.id.in_(winner_ids))).all()
        }

    recent_matches = []
    for match in matches:
        top_score = session.exec(
            select(sqlalchemy_func.coalesce(sqlalchemy_func.max(MatchPlayer.score), 0))
            .where(MatchPlayer.match_id == match.id)
        ).one()
        winner = winners.get(match.winner_user_id)
        recent_matches.append(
            PublicDashboardRecentMatch(
                match_id=int(match.id),
                mode=match.mode,
                winner_display_name=winner.display_name if winner else None,
                top_score=int(top_score or 0),
                finished_at=match.ends_at,
            )
        )
    return recent_matches


@router.get("/dashboard", response_model=PublicDashboardRead)
def read_public_dashboard(session: Session = Depends(get_session)):
    return PublicDashboardRead(
        updated_at=utc_now(),
        leaderboard=build_public_leaderboard(session),
        highlights=build_public_highlights(session),
        recent_matches=build_public_recent_matches(session),
    )
