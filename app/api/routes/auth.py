from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import CurrentUser
from app.core.database import get_db
from app.core.security import hash_password, hash_session_token, verify_password
from app.models.admin import AuthSession
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, LogoutResponse, ResetPasswordRequest
from app.schemas.user import UserCreate, UserRead
from app.services.audit_service import record_audit

router = APIRouter()
SESSION_COOKIE_NAME = "studio_session"
SESSION_TTL_DAYS = 14


def _issue_session(user: User, db: Session, request: Request) -> tuple[str, AuthSession]:
    token = f"sts_{datetime.now(timezone.utc).timestamp():.0f}_{user.id}_{hash_session_token(user.username)[:12]}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(token),
        expires_at=expires_at,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(session)
    return token, session


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    stmt = select(User).options(selectinload(User.memberships)).where(User.username == payload.username)
    user = db.scalar(stmt)
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    token, session = _issue_session(user, db, request)
    user.last_login_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user_id=user.id,
        action="auth.login",
        target_type="user",
        target_id=user.id,
        summary=f"User {user.username} logged in",
    )
    db.commit()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
    )
    return LoginResponse(token=token, expires_at=session.expires_at, user=user)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> LogoutResponse:
    auth_header = request.headers.get("authorization")
    raw_token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        raw_token = auth_header[7:].strip()
    raw_token = raw_token or request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token:
        stmt = select(AuthSession).where(AuthSession.token_hash == hash_session_token(raw_token), AuthSession.revoked_at.is_(None))
        session = db.scalar(stmt)
        if session:
            session.revoked_at = datetime.now(timezone.utc)
    record_audit(
        db,
        user_id=current_user.id,
        action="auth.logout",
        target_type="user",
        target_id=current_user.id,
        summary=f"User {current_user.username} logged out",
    )
    db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME)
    return LogoutResponse(success=True)


@router.get("/me", response_model=UserRead)
def get_me(current_user: CurrentUser, db: Session = Depends(get_db)) -> User:
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == current_user.id)
    return db.scalar(stmt)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    duplicate = db.scalar(select(User).where(User.username == payload.username))
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        email=payload.email,
        role=payload.role,
        password_hash=hash_password(payload.password or "changeme123"),
        is_active=payload.is_active,
    )
    db.add(user)
    record_audit(
        db,
        user_id=user.id,
        action="auth.register",
        target_type="user",
        target_id=None,
        summary=f"Registered user {payload.username}",
    )
    db.commit()
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user.id)
    return db.scalar(stmt)


@router.post("/change-password", response_model=UserRead)
def change_password(
    payload: ChangePasswordRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, current_user.id)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    record_audit(
        db,
        user_id=current_user.id,
        action="auth.change_password",
        target_type="user",
        target_id=current_user.id,
        summary=f"Changed password for {current_user.username}",
    )
    db.commit()
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user.id)
    return db.scalar(stmt)


@router.post("/reset-password", response_model=UserRead)
def self_reset_password(
    payload: ResetPasswordRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, current_user.id)
    user.password_hash = hash_password(payload.new_password)
    record_audit(
        db,
        user_id=current_user.id,
        action="auth.self_reset_password",
        target_type="user",
        target_id=current_user.id,
        summary=f"Reset own password for {current_user.username}",
    )
    db.commit()
    stmt = select(User).options(selectinload(User.memberships)).where(User.id == user.id)
    return db.scalar(stmt)
