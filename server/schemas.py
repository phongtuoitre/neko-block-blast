from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


def validate_username_value(value: str) -> str:
    username = value.strip()
    if not 3 <= len(username) <= 20:
        raise ValueError("Username must be 3 to 20 characters long")
    if not all(char.isascii() and (char.isalnum() or char == "_") for char in username):
        raise ValueError("Username may only contain letters, numbers, and underscores")
    return username


def validate_gmail_value(value: str) -> str:
    email = str(value).strip().casefold()
    if not email.endswith("@gmail.com"):
        raise ValueError("Vui lòng sử dụng địa chỉ Gmail.")
    return email


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=20)
    display_name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        return validate_username_value(value)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        display_name = value.strip()
        if not display_name:
            raise ValueError("Display name is required")
        return display_name

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, value: EmailStr) -> str:
        return validate_gmail_value(value)


class UserRead(BaseModel):
    id: int
    username: str
    display_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, value: EmailStr) -> str:
        return validate_gmail_value(value)


class ForgotPasswordResponse(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8)

    @field_validator("email")
    @classmethod
    def validate_gmail(cls, value: EmailStr) -> str:
        return validate_gmail_value(value)


class ResetPasswordResponse(BaseModel):
    message: str


class RoomCreate(BaseModel):
    mode: str

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in ("1v1", "2v2"):
            raise ValueError("Mode must be 1v1 or 2v2")
        return value


class RoomPlayerRead(BaseModel):
    user_id: int
    username: str
    display_name: str
    team: int
    is_ready: bool
    is_host: bool


class RoomRead(BaseModel):
    room_code: str
    mode: str
    status: str
    host_user_id: int
    players: list[RoomPlayerRead]


class RoomLeaveResponse(BaseModel):
    success: bool


class MatchScoreUpdate(BaseModel):
    score: int = Field(ge=0)


class MatchPlayerRead(BaseModel):
    user_id: int
    username: str
    display_name: str
    team: int
    score: int
    result: str | None


class MatchRead(BaseModel):
    match_id: int
    room_code: str
    mode: str
    status: str
    remaining_seconds: int
    winner_user_id: int | None
    winner_team: int | None
    players: list[MatchPlayerRead]
    event_blob_uploaded: bool | None = None
    event_blob_path: str | None = None


class PublicDashboardLeaderboardItem(BaseModel):
    rank: int
    user_id: int
    username: str
    display_name: str
    matches: int
    wins: int
    total_score: int
    best_score: int


class PublicDashboardHighlight(BaseModel):
    display_name: str | None = None
    value: int = 0


class PublicDashboardHighlights(BaseModel):
    highest_score: PublicDashboardHighlight
    most_matches: PublicDashboardHighlight
    most_wins: PublicDashboardHighlight


class PublicDashboardRecentMatch(BaseModel):
    match_id: int
    mode: str
    winner_display_name: str | None = None
    top_score: int
    finished_at: datetime | None = None


class PublicDashboardRead(BaseModel):
    updated_at: datetime
    leaderboard: list[PublicDashboardLeaderboardItem]
    highlights: PublicDashboardHighlights
    recent_matches: list[PublicDashboardRecentMatch]
