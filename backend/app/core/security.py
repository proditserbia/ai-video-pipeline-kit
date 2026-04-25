from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_BCRYPT_MAX_BYTES = 72


def validate_password_length(password: str) -> None:
    """Raise ValueError if *password* exceeds bcrypt's 72-byte hard limit.

    bcrypt silently truncates (or in newer library versions, raises an error)
    for inputs longer than 72 bytes.  We catch this early so callers receive a
    clear, actionable message rather than a cryptic library exception.
    """
    if len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password must be at most {_BCRYPT_MAX_BYTES} bytes when encoded as "
            "UTF-8 (bcrypt hard limit). Please choose a shorter password."
        )


def hash_password(password: str) -> str:
    validate_password_length(password)
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str | int, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT. Raises JWTError on failure."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise
