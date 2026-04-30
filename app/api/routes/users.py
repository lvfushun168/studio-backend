from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import ADMIN_ROLES, CurrentUser, generate_api_key, require_project_access, require_role
from app.core.database import get_db
from app.core.security import hash_password
from app.models.project import UserProjectMembership
from app.models.user import User
from app.schemas.auth import ResetPasswordRequest
from app.schemas.user import UserCreate, UserMeRead, UserRead, UserUpdate
from app.services.audit_service import record_audit

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

    stmt = select(User).options(selectinload(User.memberships)).order_by(User.id)
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
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user_id)
    user = db.scalar(stmt)
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
        password_hash=hash_password(payload.password) if payload.password else None,
        is_active=payload.is_active,
    )
    db.add(user)
    db.flush()
    for project_id in payload.project_ids:
        db.add(
            UserProjectMembership(
                user_id=user.id,
                project_id=project_id,
                role_in_project=payload.role,
            )
        )
    record_audit(
        db,
        user_id=current_user.id,
        action="user.create",
        target_type="user",
        target_id=user.id,
        summary=f"Created user {user.username}",
        payload_json={"projectIds": payload.project_ids, "role": payload.role},
    )
    db.commit()
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user.id)
    return db.scalar(stmt)


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    require_role(ADMIN_ROLES)(current_user)
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user_id)
    user = db.scalar(stmt)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if payload.username is not None:
        user.username = payload.username
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password:
        user.password_hash = hash_password(payload.password)
    if payload.project_ids is not None:
        existing = {m.project_id: m for m in user.memberships}
        desired = set(payload.project_ids)
        for membership in list(user.memberships):
            if membership.project_id not in desired:
                db.delete(membership)
        for project_id in desired:
            if project_id not in existing:
                db.add(
                    UserProjectMembership(
                        user_id=user.id,
                        project_id=project_id,
                        role_in_project=payload.role or user.role,
                    )
                )
    record_audit(
        db,
        user_id=current_user.id,
        action="user.update",
        target_type="user",
        target_id=user.id,
        summary=f"Updated user {user.username}",
    )
    db.commit()
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user.id)
    return db.scalar(stmt)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    require_role(ADMIN_ROLES)(current_user)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    record_audit(
        db,
        user_id=current_user.id,
        action="user.delete",
        target_type="user",
        target_id=user.id,
        summary=f"Deleted user {user.username}",
    )
    db.delete(user)
    db.commit()


@router.post("/{user_id}/reset-password", response_model=UserRead)
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    require_role(ADMIN_ROLES)(current_user)
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user_id)
    user = db.scalar(stmt)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.password_hash = hash_password(payload.new_password)
    record_audit(
        db,
        user_id=current_user.id,
        action="user.reset_password",
        target_type="user",
        target_id=user.id,
        summary=f"Reset password for {user.username}",
    )
    db.commit()
    return user


@router.post("/{user_id}/rotate-api-key", response_model=UserRead)
def rotate_user_api_key(
    user_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    require_role(ADMIN_ROLES)(current_user)
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user_id)
    user = db.scalar(stmt)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.api_key = generate_api_key()
    record_audit(
        db,
        user_id=current_user.id,
        action="user.rotate_api_key",
        target_type="user",
        target_id=user.id,
        summary=f"Rotated API key for {user.username}",
    )
    db.commit()
    return user
