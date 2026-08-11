from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=20)
    display_name: str = Field(max_length=80)
    email: str = Field(index=True, unique=True, max_length=255)
    password_hash: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Room(SQLModel, table=True):
    __tablename__ = "rooms"

    id: Optional[int] = Field(default=None, primary_key=True)
    room_code: str = Field(index=True, unique=True, max_length=6)
    mode: str = Field(max_length=3)
    host_user_id: int = Field(foreign_key="users.id")
    status: str = Field(default="waiting", max_length=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoomPlayer(SQLModel, table=True):
    __tablename__ = "room_players"
    __table_args__ = (UniqueConstraint("room_id", "user_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="rooms.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    team: int
    is_ready: bool = Field(default=False)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Match(SQLModel, table=True):
    __tablename__ = "matches"

    id: Optional[int] = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="rooms.id", index=True)
    mode: str = Field(max_length=3)
    status: str = Field(default="playing", max_length=10)
    started_at: datetime
    ends_at: datetime
    winner_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    winner_team: Optional[int] = Field(default=None)


class MatchPlayer(SQLModel, table=True):
    __tablename__ = "match_players"
    __table_args__ = (UniqueConstraint("match_id", "user_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    team: int
    score: int = Field(default=0)
    result: Optional[str] = Field(default=None, max_length=5)
    no_moves: bool = Field(default=False)


class PasswordResetCode(SQLModel, table=True):
    __tablename__ = "password_reset_codes"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    code_hash: str = Field(max_length=64)
    expires_at: datetime
    used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempts: int = Field(default=0)
