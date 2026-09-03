from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import get_db
from app.db.models import User


class AuthenticationError(Exception):
    """A deliberately detail-free authentication failure."""


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    display_name: str | None
    picture_url: str | None


def verify_google_identity(credential: str) -> GoogleIdentity:
    client_id = settings.GOOGLE_AUTH_CLIENT_ID.strip()
    if not client_id:
        raise AuthenticationError("Google authentication is not configured")
    try:
        claims = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audience=client_id,
        )
    except Exception as exc:
        raise AuthenticationError("Invalid Google credential") from exc

    issuer = claims.get("iss")
    subject = claims.get("sub")
    email = claims.get("email")
    verified = claims.get("email_verified") is True or claims.get("email_verified") == "true"
    expires_at = claims.get("exp")
    if claims.get("aud") != client_id:
        raise AuthenticationError("Invalid Google credential")
    if issuer not in {"accounts.google.com", "https://accounts.google.com"}:
        raise AuthenticationError("Invalid Google credential")
    if not isinstance(expires_at, (int, float)) or expires_at <= datetime.now(timezone.utc).timestamp():
        raise AuthenticationError("Invalid Google credential")
    if not subject or not isinstance(subject, str):
        raise AuthenticationError("Invalid Google credential")
    if not email or not isinstance(email, str):
        raise AuthenticationError("Invalid Google credential")
    if settings.GOOGLE_AUTH_REQUIRE_VERIFIED_EMAIL and not verified:
        raise AuthenticationError("Invalid Google credential")
    return GoogleIdentity(
        subject=subject,
        email=email,
        email_verified=verified,
        display_name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        picture_url=claims.get("picture") if isinstance(claims.get("picture"), str) else None,
    )


def _jwt_secret() -> str:
    secret = settings.CHRONO_JWT_SECRET
    if not secret:
        raise AuthenticationError("Chrono authentication is not configured")
    return secret


def _jwt_algorithm() -> str:
    algorithm = settings.CHRONO_JWT_ALGORITHM
    if algorithm not in {"HS256", "HS384", "HS512"}:
        raise AuthenticationError("Chrono authentication is not configured")
    return algorithm


def issue_access_token(user: User, *, now: datetime | None = None) -> tuple[str, int]:
    issued_at = now or datetime.now(timezone.utc)
    expires = issued_at + timedelta(minutes=settings.CHRONO_ACCESS_TOKEN_MINUTES)
    token = jwt.encode(
        {
            "sub": str(user.id),
            "type": "access",
            "iss": "chrono",
            "iat": issued_at,
            "exp": expires,
        },
        _jwt_secret(),
        algorithm=_jwt_algorithm(),
    )
    return token, max(0, int((expires - issued_at).total_seconds()))


def decode_access_token(token: str) -> UUID:
    try:
        claims = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[_jwt_algorithm()],
            issuer="chrono",
            options={"require": ["sub", "type", "iat", "exp", "iss"]},
        )
        if claims.get("type") != "access":
            raise AuthenticationError("Invalid access token")
        return UUID(str(claims["sub"]))
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Invalid access token") from exc


bearer_scheme = HTTPBearer(auto_error=False, description="Chrono access token")


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise _unauthorized()
    try:
        user_id = decode_access_token(credentials.credentials)
    except AuthenticationError:
        raise _unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user
