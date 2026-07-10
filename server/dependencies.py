import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from server.database import get_session
from server.models import User
from server.security import decode_access_token


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        username_key = payload.get("sub")
    except (jwt.InvalidTokenError, RuntimeError):
        raise credentials_error

    if not username_key:
        raise credentials_error

    user = session.exec(select(User).where(User.username == username_key)).first()
    if not user or not user.is_active:
        raise credentials_error

    return user
