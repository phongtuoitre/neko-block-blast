from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from server.database import get_session
from server.dependencies import get_current_user
from server.match_result_events import (
    MatchResultBlobStatus,
    upload_match_result_blob_from_rows,
)
from server.models import Match, MatchPlayer, Room, User
from server.schemas import MatchPlayerRead, MatchRead, MatchScoreUpdate


router = APIRouter(prefix="/matches", tags=["matches"])


def utc_now():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def finalize_match(session: Session, match: Match, now=None) -> Match:
    current_time = as_utc(now or utc_now())
    if match.status != "playing" or current_time < as_utc(match.ends_at):
        return match

    players = session.exec(
        select(MatchPlayer).where(MatchPlayer.match_id == match.id)
    ).all()
    highest_score = max((player.score for player in players), default=0)
    winners = [player for player in players if player.score == highest_score]

    match.status = "finished"
    if len(winners) == 1:
        winner = winners[0]
        match.winner_user_id = winner.user_id
        match.winner_team = winner.team
        for player in players:
            player.result = "win" if player.user_id == winner.user_id else "lose"
            session.add(player)
    else:
        match.winner_user_id = None
        match.winner_team = None
        for player in players:
            player.result = "draw"
            session.add(player)

    room = session.get(Room, match.room_id)
    if room:
        room.status = "finished"
        session.add(room)
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


def build_match_response(session: Session, match: Match, now=None) -> MatchRead:
    current_time = as_utc(now or utc_now())
    match = finalize_match(session, match, current_time)
    room = session.get(Room, match.room_id)
    rows = session.exec(
        select(MatchPlayer, User)
        .join(User, User.id == MatchPlayer.user_id)
        .where(MatchPlayer.match_id == match.id)
        .order_by(MatchPlayer.team, MatchPlayer.id)
    ).all()
    remaining_seconds = max(
        0, int((as_utc(match.ends_at) - current_time).total_seconds())
    )
    event_blob_status = publish_finished_match_result_blob(match, room, rows)
    return MatchRead(
        match_id=match.id,
        room_code=room.room_code if room else "",
        mode=match.mode,
        status=match.status,
        remaining_seconds=remaining_seconds,
        winner_user_id=match.winner_user_id,
        winner_team=match.winner_team,
        players=[
            MatchPlayerRead(
                user_id=user.id,
                username=user.username,
                display_name=user.display_name,
                team=match_player.team,
                score=match_player.score,
                result=match_player.result,
            )
            for match_player, user in rows
        ],
        event_blob_uploaded=event_blob_status.uploaded,
        event_blob_path=event_blob_status.path,
    )


def publish_finished_match_result_blob(match, room, rows) -> MatchResultBlobStatus:
    if match.status != "finished":
        return MatchResultBlobStatus(uploaded=False, path=None)
    return upload_match_result_blob_from_rows(match, room, rows)


def get_match_or_404(session: Session, match_id: int) -> Match:
    match = session.get(Match, match_id)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match not found",
        )
    return match


def require_match_player(session: Session, match: Match, user_id: int) -> MatchPlayer:
    player = session.exec(
        select(MatchPlayer).where(
            MatchPlayer.match_id == match.id,
            MatchPlayer.user_id == user_id,
        )
    ).first()
    if not player:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not in match",
        )
    return player


@router.post("/{match_id}/score", response_model=MatchRead)
def submit_match_score(
    match_id: int,
    payload: MatchScoreUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    match = get_match_or_404(session, match_id)
    match = finalize_match(session, match)
    player = require_match_player(session, match, current_user.id)
    if match.status != "playing":
        room = session.get(Room, match.room_id)
        rows = session.exec(
            select(MatchPlayer, User)
            .join(User, User.id == MatchPlayer.user_id)
            .where(MatchPlayer.match_id == match.id)
            .order_by(MatchPlayer.team, MatchPlayer.id)
        ).all()
        publish_finished_match_result_blob(match, room, rows)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Match is not playing",
        )
    if payload.score < player.score:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Score cannot decrease",
        )
    if payload.score > player.score:
        player.score = payload.score
        session.add(player)
        session.commit()
    return build_match_response(session, match)


@router.get("/{match_id}", response_model=MatchRead)
def read_match(
    match_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    match = get_match_or_404(session, match_id)
    require_match_player(session, match, current_user.id)
    return build_match_response(session, match)
