"""Authentication and authorization utilities."""

import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.project import UserProjectMembership
from app.models.user import User

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


async def get_current_user(
    x_user_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Depends(api_key_header)] = None,
    db: Session = Depends(get_db),
) -> User:
    """Resolve current user from headers.

    Priority:
    1. X-User-ID header (development mode - direct user ID)
    2. X-API-Key header or API-Key query param
    """
    # Development mode: direct user ID
    if x_user_id is not None:
        try:
            user_id = int(x_user_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-User-ID header",
            )
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user

    # API Key mode
    key = x_api_key or api_key
    if key:
        stmt = select(User).where(User.api_key == key, User.is_active == True)
        user = db.scalar(stmt)
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Fallback: return first admin for backward compatibility during transition
    stmt = select(User).where(User.role == "admin", User.is_active == True).order_by(User.id)
    user = db.scalar(stmt)
    if user:
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


CurrentUser = Annotated[User, Depends(get_current_user)]


# Role-based permission helpers

ADMIN_ROLES = {"admin"}
DIRECTOR_ROLES = {"admin", "director"}
PRODUCER_ROLES = {"admin", "producer"}
DIRECTOR_PRODUCER_ROLES = {"admin", "director", "producer"}
ARTIST_ROLES = {"admin", "director", "producer", "artist"}
ALL_ROLES = {"admin", "director", "producer", "artist", "visitor"}


def require_role(allowed_roles: set[str]):
    def checker(user: CurrentUser) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not allowed for this operation",
            )
        return user
    return checker


def require_project_member(
    project_id: int,
    user: CurrentUser,
    db: Session,
    allowed_roles: set[str] | None = None,
) -> None:
    """Check if user is a member of the project with sufficient role."""
    # Admin bypass
    if user.role == "admin":
        return

    # Check membership
    stmt = select(UserProjectMembership).where(
        UserProjectMembership.user_id == user.id,
        UserProjectMembership.project_id == project_id,
    )
    membership = db.scalar(stmt)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this project",
        )

    # Check role if specified
    if allowed_roles:
        effective_role = membership.role_in_project or user.role
        if effective_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this project",
            )


def require_project_access(project_id: int, user: CurrentUser, db: Session) -> None:
    """Basic project access check (any member or admin)."""
    if user.role == "admin":
        return
    stmt = select(UserProjectMembership).where(
        UserProjectMembership.user_id == user.id,
        UserProjectMembership.project_id == project_id,
    )
    if not db.scalar(stmt):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project access denied",
        )


def is_project_member(project_id: int, user: User, db: Session) -> bool:
    if user.role == "admin":
        return True
    stmt = select(UserProjectMembership).where(
        UserProjectMembership.user_id == user.id,
        UserProjectMembership.project_id == project_id,
    )
    return db.scalar(stmt) is not None
