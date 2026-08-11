from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from server.database import get_session
from server.dependencies import get_current_user
from server.match_result_events import (
    MatchResultBlobStatus,
    upload_match_result_blob_from_rows,
)
from server.models import Match, MatchPlayer, Room, RoomPlayer, User
from server.schemas import MatchPlayerRead, MatchRead, MatchScoreUpdate


router = APIRouter(prefix="/matches", tags=["matches"])
MATCH_DURATION_SECONDS = 120


def utc_now():
    return datetime.now(timezone.utc)


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_playing_match(
    session: Session,
    room: Room,
    room_players: list[RoomPlayer],
    started_at=None,
) -> Match:
    started_at = as_utc(started_at or utc_now())
    match = Match(
        room_id=room.id,
        mode=room.mode,
        status="playing",
        started_at=started_at,
        ends_at=started_at + timedelta(seconds=MATCH_DURATION_SECONDS),
    )
    session.add(match)
    session.flush()
    for room_player in room_players:
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=room_player.user_id,
                team=room_player.team,
            )
        )
        room_player.is_ready = False
        session.add(room_player)
    room.status = "playing"
    session.add(room)
    return match


def all_match_players_have_no_moves(session: Session, match: Match) -> bool:
    players = session.exec(
        select(MatchPlayer).where(MatchPlayer.match_id == match.id)
    ).all()
    if not players:
        return False
    return all(player.no_moves for player in players)


def finalize_match(
    session: Session,
    match: Match,
    now=None,
    force: bool = False,
) -> Match:
    current_time = as_utc(now or utc_now())
    if match.status != "playing":
        return match
    if not force and current_time < as_utc(match.ends_at):
        return match

    players = session.exec(
        select(MatchPlayer).where(MatchPlayer.match_id == match.id)
    ).all()
    highest_score = max((player.score for player in players), default=0)
    winners = [player for player in players if player.score == highest_score]

    match.status = "finished"
    if force and current_time < as_utc(match.ends_at):
        match.ends_at = current_time
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
        room.status = "waiting"
        session.add(room)
        room_players = session.exec(
            select(RoomPlayer).where(RoomPlayer.room_id == room.id)
        ).all()
        for room_player in room_players:
            room_player.is_ready = False
            session.add(room_player)
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
    rematch_by_user = {}
    next_match_id = None
    if room:
        room_players = session.exec(
            select(RoomPlayer).where(RoomPlayer.room_id == room.id)
        ).all()
        rematch_by_user = {
            room_player.user_id: room_player.is_ready for room_player in room_players
        }
        next_match = session.exec(
            select(Match)
            .where(
                Match.room_id == room.id,
                Match.status == "playing",
                Match.id != match.id,
            )
            .order_by(Match.id.desc())
        ).first()
        if next_match:
            next_match_id = next_match.id
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
                no_moves=bool(match_player.no_moves),
                wants_rematch=bool(rematch_by_user.get(user.id, False)),
            )
            for match_player, user in rows
        ],
        next_match_id=next_match_id,
        event_blob_uploaded=event_blob_status.uploaded,
        event_blob_path=event_blob_status.path,
    )


def publish_finished_match_result_blob(match, room, rows) -> MatchResultBlobStatus:
    if match.status != "finished":
        return MatchResultBlobStatus(uploaded=False, path=None)
    return upload_match_result_blob_from_rows(match, room, rows)


def get_match_or_404(
    session: Session,
    match_id: int,
    for_update: bool = False,
) -> Match:
    if for_update:
        match = session.exec(
            select(Match).where(Match.id == match_id).with_for_update()
        ).first()
    else:
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
    match = get_match_or_404(session, match_id, for_update=True)
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
    score_changed = payload.score > player.score
    if score_changed:
        player.score = payload.score
        session.add(player)
    if payload.no_moves is not None:
        player.no_moves = payload.no_moves
        session.add(player)
    if score_changed or payload.no_moves is not None:
        session.commit()
    if payload.no_moves and all_match_players_have_no_moves(session, match):
        match = finalize_match(session, match, force=True)
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


@router.post("/{match_id}/rematch", response_model=MatchRead)
def request_match_rematch(
    match_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    match = get_match_or_404(session, match_id, for_update=True)
    match = finalize_match(session, match)
    require_match_player(session, match, current_user.id)
    if match.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Match is not finished",
        )

    room = session.exec(
        select(Room).where(Room.id == match.room_id).with_for_update()
    ).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    room_players = session.exec(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room.id)
        .order_by(RoomPlayer.joined_at, RoomPlayer.id)
    ).all()
    current_room_player = next(
        (
            room_player
            for room_player in room_players
            if room_player.user_id == current_user.id
        ),
        None,
    )
    if current_room_player is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Player is not in room",
        )
    if len(room_players) != 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room requires exactly 2 players",
        )

    active_match = session.exec(
        select(Match)
        .where(Match.room_id == room.id, Match.status == "playing")
        .order_by(Match.id.desc())
    ).first()
    if active_match:
        return build_match_response(session, active_match)

    current_room_player.is_ready = True
    room.status = "waiting"
    session.add(current_room_player)
    session.add(room)

    if all(room_player.is_ready for room_player in room_players):
        new_match = create_playing_match(session, room, room_players)
        session.commit()
        session.refresh(new_match)
        return build_match_response(session, new_match)

    session.commit()
    session.refresh(match)
    return build_match_response(session, match)
