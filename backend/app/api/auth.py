from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User
from app.schemas.auth import AuthResponse, GoogleLoginRequest, PublicUser
from app.services.auth import (
    AuthenticationError,
    get_current_user,
    issue_access_token,
    verify_google_identity,
)


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/google", response_model=AuthResponse)
def google_login(data: GoogleLoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    try:
        identity = verify_google_identity(data.credential)
    except AuthenticationError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential")

    user = db.query(User).filter(User.google_subject == identity.subject).one_or_none()
    if user is None:
        user = User(
            google_subject=identity.subject,
            email=identity.email,
            email_verified=identity.email_verified,
            display_name=identity.display_name,
            picture_url=identity.picture_url,
            is_active=True,
        )
        db.add(user)
    else:
        user.email = identity.email
        user.email_verified = identity.email_verified
        user.display_name = identity.display_name
        user.picture_url = identity.picture_url
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        db.flush()
        token, expires_in = issue_access_token(user)
    except AuthenticationError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    db.commit()
    db.refresh(user)
    return AuthResponse(access_token=token, expires_in=expires_in, user=PublicUser.model_validate(user))


@router.get("/me", response_model=PublicUser)
def auth_me(current_user: User = Depends(get_current_user)) -> PublicUser:
    return PublicUser.model_validate(current_user)
