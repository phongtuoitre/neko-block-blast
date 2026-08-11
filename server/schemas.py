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
    no_moves: bool | None = None


class MatchPlayerRead(BaseModel):
    user_id: int
    username: str
    display_name: str
    team: int
    score: int
    result: str | None
    no_moves: bool = False
    wants_rematch: bool = False


class MatchRead(BaseModel):
    match_id: int
    room_code: str
    mode: str
    status: str
    remaining_seconds: int
    winner_user_id: int | None
    winner_team: int | None
    players: list[MatchPlayerRead]
    next_match_id: int | None = None
    event_blob_uploaded: bool | None = None
    event_blob_path: str | None = None


class AIGuideGameState(BaseModel):
    score: int = Field(default=0, ge=0, le=10_000_000)
    board: list[list[int]] | None = None
    current_blocks: list[list[list[int]]] | None = Field(default=None, max_length=3)
    combo: int | None = Field(default=None, ge=0, le=999)

    @field_validator("board")
    @classmethod
    def validate_board(cls, value: list[list[int]] | None):
        if value is None:
            return value
        if not 1 <= len(value) <= 10:
            raise ValueError("Board must contain 1 to 10 rows")
        row_length = len(value[0]) if value and isinstance(value[0], list) else 0
        if not 1 <= row_length <= 10:
            raise ValueError("Board rows must contain 1 to 10 cells")
        normalized_board = []
        for row in value:
            if len(row) != row_length:
                raise ValueError("Board rows must have the same length")
            normalized_board.append([1 if int(cell) else 0 for cell in row])
        return normalized_board

    @field_validator("current_blocks")
    @classmethod
    def validate_current_blocks(cls, value: list[list[list[int]]] | None):
        if value is None:
            return value

        normalized_blocks = []
        for block in value:
            if not 1 <= len(block) <= 5:
                raise ValueError("Each block must contain 1 to 5 rows")
            row_length = len(block[0]) if block and isinstance(block[0], list) else 0
            if not 1 <= row_length <= 5:
                raise ValueError("Each block row must contain 1 to 5 cells")
            normalized_block = []
            for row in block:
                if len(row) != row_length:
                    raise ValueError("Block rows must have the same length")
                normalized_block.append([1 if int(cell) else 0 for cell in row])
            normalized_blocks.append(normalized_block)
        return normalized_blocks


class AIGuideChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    game_state: AIGuideGameState | None = None

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("Question is required")
        return question


class AIGuideChatResponse(BaseModel):
    reply: str
    source: str
    used_fallback: bool
    error: str | None = None


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
