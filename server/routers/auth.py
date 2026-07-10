from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlmodel import Session, select

from server.database import get_session
from server.dependencies import get_current_user
from server.email_service import send_password_reset_email
from server.models import PasswordResetCode, User
from server.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    Token,
    UserCreate,
    UserRead,
    validate_username_value,
)
from server.security import (
    create_access_token,
    hash_password,
    hash_reset_code,
    verify_password,
    verify_reset_code,
)


router = APIRouter(prefix="/auth", tags=["auth"])
FORGOT_PASSWORD_MESSAGE = "Nếu email tồn tại, mã xác thực đã được gửi."
MAX_RESET_ATTEMPTS = 5


def get_user_by_username(session: Session, username: str) -> User | None:
    return session.exec(
        select(User).where(func.lower(User.username) == username.strip().casefold())
    ).first()


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.exec(
        select(User).where(func.lower(User.email) == email.strip().casefold())
    ).first()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(payload: UserCreate, session: Session = Depends(get_session)):
    username = validate_username_value(payload.username)
    email = payload.email.strip().casefold()

    if get_user_by_username(session, username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    if get_user_by_email(session, email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        username=username,
        display_name=payload.display_name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login_user(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    username = form_data.username.strip()
    user = get_user_by_username(session, username)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Token(access_token=create_access_token(user.username), token_type="bearer")


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)):
    return current_user


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    session: Session = Depends(get_session),
):
    email = str(payload.email).strip().casefold()
    user = get_user_by_email(session, email)
    if not user:
        return ForgotPasswordResponse(message=FORGOT_PASSWORD_MESSAGE)

    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now(timezone.utc)
    reset_code = PasswordResetCode(
        user_id=user.id,
        code_hash=hash_reset_code(code),
        expires_at=now + timedelta(minutes=10),
    )
    session.add(reset_code)
    session.commit()
    try:
        send_password_reset_email(email, code)
    except (OSError, RuntimeError) as exc:
        session.delete(reset_code)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Không thể gửi email xác thực: {exc}",
        ) from exc

    return ForgotPasswordResponse(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    payload: ResetPasswordRequest,
    session: Session = Depends(get_session),
):
    email = str(payload.email).strip().casefold()
    user = get_user_by_email(session, email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã xác thực không hợp lệ hoặc đã hết hạn.",
        )

    reset_code = session.exec(
        select(PasswordResetCode)
        .where(
            PasswordResetCode.user_id == user.id,
            PasswordResetCode.used_at.is_(None),
        )
        .order_by(PasswordResetCode.created_at.desc())
    ).first()
    now = datetime.now(timezone.utc)
    if not reset_code or as_utc(reset_code.expires_at) <= now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã xác thực không hợp lệ hoặc đã hết hạn.",
        )
    if reset_code.attempts >= MAX_RESET_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Đã vượt quá số lần thử mã xác thực.",
        )
    if not verify_reset_code(payload.code, reset_code.code_hash):
        reset_code.attempts += 1
        session.add(reset_code)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã xác thực không hợp lệ.",
        )

    user.password_hash = hash_password(payload.new_password)
    reset_code.used_at = now
    session.add(user)
    session.add(reset_code)
    session.commit()
    return ResetPasswordResponse(
        message="Đổi mật khẩu thành công. Vui lòng đăng nhập lại."
    )
