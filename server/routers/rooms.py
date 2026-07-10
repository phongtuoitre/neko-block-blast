import secrets
import string
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from server.database import get_session
from server.dependencies import get_current_user
from server.models import Match, MatchPlayer, Room, RoomPlayer, User
from server.routers.matches import build_match_response, utc_now
from server.schemas import MatchRead, RoomCreate, RoomLeaveResponse, RoomPlayerRead, RoomRead


router = APIRouter(prefix="/rooms", tags=["rooms"])

ROOM_CODE_ALPHABET = string.ascii_uppercase + string.digits


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

    session.delete(room_player)
    session.flush()
    remaining_players = session.exec(
        select(RoomPlayer)
        .where(RoomPlayer.room_id == room.id)
        .order_by(RoomPlayer.joined_at, RoomPlayer.id)
    ).all()
    if not remaining_players:
        session.delete(room)
    elif room.host_user_id == current_user.id:
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
        select(RoomPlayer).where(RoomPlayer.room_id == room.id)
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

    started_at = utc_now()
    match = Match(
        room_id=room.id,
        mode=room.mode,
        status="playing",
        started_at=started_at,
        ends_at=started_at + timedelta(seconds=120),
    )
    session.add(match)
    session.flush()
    for player in players:
        session.add(
            MatchPlayer(
                match_id=match.id,
                user_id=player.user_id,
                team=player.team,
            )
        )
    room.status = "playing"
    session.add(room)
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
