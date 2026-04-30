from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import ADMIN_ROLES, CurrentUser, generate_api_key, require_project_access, require_role
from app.core.database import get_db
from app.models.project import UserProjectMembership
from app.models.user import User
from app.schemas.user import UserCreate, UserMeRead, UserRead

router = APIRouter()


@router.get("/me", response_model=UserMeRead)
def get_current_user_me(current_user: CurrentUser) -> User:
    return current_user


@router.get("", response_model=list[UserRead])
def list_users(
    project_id: int | None = None,
    role: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[User]:
    if project_id is None:
        require_role(ADMIN_ROLES)(current_user)

    stmt = select(User).order_by(User.id)
    if project_id is not None:
        if current_user and current_user.role != "admin":
            require_project_access(project_id, current_user, db)
        stmt = (
            select(User)
            .join(UserProjectMembership, UserProjectMembership.user_id == User.id)
            .where(UserProjectMembership.project_id == project_id)
            .order_by(User.id)
        )
    if role is not None:
        stmt = stmt.where(User.role == role)
    return list(db.scalars(stmt).all())


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    require_role(ADMIN_ROLES)(current_user)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    require_role(ADMIN_ROLES)(current_user)
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        role=payload.role,
        api_key=generate_api_key(),
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    require_role(ADMIN_ROLES)(current_user)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.username = payload.username
    user.display_name = payload.display_name
    user.email = payload.email
    user.role = payload.role
    user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user
