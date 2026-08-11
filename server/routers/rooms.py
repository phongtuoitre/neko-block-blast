import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from server.database import get_session
from server.dependencies import get_current_user
from server.models import Match, MatchPlayer, Room, RoomPlayer, User
from server.routers.matches import build_match_response, create_playing_match, utc_now
from server.schemas import MatchRead, RoomCreate, RoomLeaveResponse, RoomPlayerRead, RoomRead


router = APIRouter(prefix="/rooms", tags=["rooms"])

ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits
TRANSIENT_MATCH_STATUSES = {"cancelled", "abandoned"}


def get_room_or_404(session: Session, room_code: str) -> Room:
    room = session.exec(
        select(Room).where(Room.room_code == room_code.strip().upper())
    ).first()
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return room


def get_room_for_leave(session: Session, room_code: str) -> Room | None:
    return session.exec(
        select(Room)
        .where(Room.room_code == room_code.strip().upper())
        .with_for_update()
    ).first()


def build_room_response(session: Session, room: Room) -> RoomRead:
    rows = session.exec(
        select(RoomPlayer, User)
        .join(User, User.id == RoomPlayer.user_id)
        .where(RoomPlayer.room_id == room.id)
        .order_by(RoomPlayer.joined_at, RoomPlayer.id)
    ).all()
    players = [
        RoomPlayerRead(
            user_id=user.id,
            username=user.username,
            display_name=user.display_name,
            team=room_player.team,
            is_ready=room_player.is_ready,
            is_host=user.id == room.host_user_id,
        )
        for room_player, user in rows
    ]
    return RoomRead(
        room_code=room.room_code,
        mode=room.mode,
        status=room.status,
        host_user_id=room.host_user_id,
        players=players,
    )


def generate_room_code(session: Session) -> str:
    for _ in range(20):
        room_code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(6))
        existing = session.exec(
            select(Room).where(Room.room_code == room_code)
        ).first()
        if not existing:
            return room_code
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Could not generate room code",
    )


def cancel_active_room_matches(session: Session, room: Room) -> bool:
    active_matches = session.exec(
        select(Match)
        .where(Match.room_id == room.id, Match.status == "playing")
        .with_for_update()
    ).all()
    if not active_matches:
        return False

    cancelled_at = utc_now()
    for match in active_matches:
        match.status = "cancelled"
        match.ends_at = cancelled_at
        match.winner_user_id = None
        match.winner_team = None
        session.add(match)
        match_players = session.exec(
            select(MatchPlayer).where(MatchPlayer.match_id == match.id)
        ).all()
        for match_player in match_players:
            if not match_player.result:
                match_player.result = "draw"
                session.add(match_player)
    return True


def delete_transient_matches_for_empty_room(session: Session, room: Room) -> bool:
    matches = session.exec(
        select(Match).where(Match.room_id == room.id).with_for_update()
    ).all()
    if any(match.status not in TRANSIENT_MATCH_STATUSES for match in matches):
        return False

    for match in matches:
        match_players = session.exec(
            select(MatchPlayer).where(MatchPlayer.match_id == match.id)
        ).all()
        for match_player in match_players:
            session.delete(match_player)
    session.flush()

    for match in matches:
        session.delete(match)
    session.flush()
    return True


@router.post("", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    room = Room(
        room_code=generate_room_code(session),
        mode=payload.mode,
        host_user_id=current_user.id,
    )
    session.add(room)
    session.commit()
    session.refresh(room)

    room_player = RoomPlayer(room_id=room.id, user_id=current_user.id, team=1)
    session.add(room_player)
    session.commit()
    return build_room_response(session, room)


@router.post("/{room_code}/join", response_model=RoomRead)
def join_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    room = get_room_or_404(session, room_code)
    existing_player = session.exec(
        select(RoomPlayer).where(
            RoomPlayer.room_id == room.id,
            RoomPlayer.user_id == current_user.id,
        )
    ).first()
    if existing_player:
        return build_room_response(session, room)
    if room.status != "waiting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room is not waiting",
        )

    players = session.exec(
        select(RoomPlayer).where(RoomPlayer.room_id == room.id)
    ).all()
    capacity = 2 if room.mode == "1v1" else 4
    team_capacity = 1 if room.mode == "1v1" else 2
    if len(players) >= capacity:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Room is full")

    team_counts = {
        1: sum(player.team == 1 for player in players),
        2: sum(player.team == 2 for player in players),
    }
    team = 1 if team_counts[1] < team_counts[2] else 2
    if team_counts[team] >= team_capacity:
        team = 2 if team == 1 else 1

    session.add(RoomPlayer(room_id=room.id, user_id=current_user.id, team=team))
    session.commit()
    return build_room_response(session, room)


@router.get("/{room_code}", response_model=RoomRead)
def read_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    room = get_room_or_404(session, room_code)
    return build_room_response(session, room)


@router.post("/{room_code}/leave", response_model=RoomLeaveResponse)
def leave_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    room = get_room_for_leave(session, room_code)
    if not room:
        return RoomLeaveResponse(success=True)

    room_player = session.exec(
        select(RoomPlayer)
        .where(
            RoomPlayer.room_id == room.id,
            RoomPlayer.user_id == current_user.id,
        )
        .with_for_update()
    ).first()
    if not room_player:
        return RoomLeaveResponse(success=True)

    match_cancelled = cancel_active_room_matches(session, room)
    session.delete(room_player)
    session.flush()
    remaining_players = session.exec(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room.id)
        .order_by(RoomPlayer.joined_at, RoomPlayer.id)
    ).all()
    if not remaining_players:
        if delete_transient_matches_for_empty_room(session, room):
            session.delete(room)
        else:
            room.status = "finished"
            session.add(room)
    else:
        for remaining_player in remaining_players:
            remaining_player.is_ready = False
            session.add(remaining_player)
        if match_cancelled or room.status == "playing":
            room.status = "waiting"
        if (
            room.host_user_id == current_user.id
            or all(player.user_id != room.host_user_id for player in remaining_players)
        ):
            room.host_user_id = remaining_players[0].user_id
        session.add(room)
    session.commit()
    return RoomLeaveResponse(success=True)


@router.post("/{room_code}/ready", response_model=RoomRead)
def toggle_ready(
    room_code: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    room = get_room_or_404(session, room_code)
    room_player = session.exec(
        select(RoomPlayer).where(
            RoomPlayer.room_id == room.id,
            RoomPlayer.user_id == current_user.id,
        )
    ).first()
    if not room_player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player is not in room",
        )
    room_player.is_ready = not room_player.is_ready
    session.add(room_player)
    session.commit()
    return build_room_response(session, room)


@router.post("/{room_code}/start", response_model=MatchRead)
def start_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    room = get_room_or_404(session, room_code)
    if room.host_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the host can start the match",
        )
    if room.mode != "1v1":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only 1v1 matches are supported",
        )
    if room.status != "waiting":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room is not waiting",
        )

    players = session.exec(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room.id)
        .order_by(RoomPlayer.team, RoomPlayer.id)
    ).all()
    if len(players) != 2:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room requires exactly 2 players",
        )
    if any(
        not player.is_ready
        for player in players
        if player.user_id != room.host_user_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="All guests must be ready",
        )

    existing_match = session.exec(
        select(Match).where(
            Match.room_id == room.id,
            Match.status == "playing",
        )
    ).first()
    if existing_match:
        return build_match_response(session, existing_match)

    match = create_playing_match(session, room, players)
    session.commit()
    session.refresh(match)
    return build_match_response(session, match)


@router.get("/{room_code}/active-match", response_model=MatchRead)
def read_active_match(
    room_code: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    room = get_room_or_404(session, room_code)
    membership = session.exec(
        select(RoomPlayer).where(
            RoomPlayer.room_id == room.id,
            RoomPlayer.user_id == current_user.id,
        )
    ).first()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not in room",
        )
    match = session.exec(
        select(Match)
        .where(Match.room_id == room.id, Match.status == "playing")
        .order_by(Match.id.desc())
    ).first()
    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active match",
        )
    return build_match_response(session, match)
