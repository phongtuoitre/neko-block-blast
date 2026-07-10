from datetime import datetime, timedelta, timezone
import hashlib
import hmac

import jwt
from pwdlib import PasswordHash

from server.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, get_secret_key


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def hash_reset_code(code: str) -> str:
    secret_key = get_secret_key()
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required")
    return hmac.new(
        secret_key.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_reset_code(code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_reset_code(code), code_hash)


def create_access_token(subject: str) -> str:
    secret_key = get_secret_key()
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    secret_key = get_secret_key()
    if not secret_key:
        raise RuntimeError("SECRET_KEY environment variable is required")

    return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
