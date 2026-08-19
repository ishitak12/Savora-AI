"""Shared FastAPI dependencies: current user and role guards."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User, UserRole

bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated or token is invalid.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _CREDENTIALS_ERROR
    payload = decode_access_token(credentials.credentials)
    if not payload or "sub" not in payload:
        raise _CREDENTIALS_ERROR
    user = db.scalar(select(User).where(User.email == payload["sub"]))
    if user is None:
        raise _CREDENTIALS_ERROR
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """403 rather than 401: the caller is authenticated, just not allowed."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an admin account.",
        )
    return user


def require_customer(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action is for customer accounts.",
        )
    return user
