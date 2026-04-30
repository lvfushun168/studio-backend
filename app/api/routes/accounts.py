from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import ADMIN_ROLES, CurrentUser, require_role
from app.core.database import get_db
from app.core.security import decrypt_secret, encrypt_secret
from app.models.admin import AccountPoolAccount, AccountProjectMembership
from app.models.project import Project
from app.schemas.admin import AccountCreate, AccountRead, AccountSyncRequest, AccountUpdate, AccountVerifyRequest
from app.services.audit_service import record_audit

router = APIRouter()


def _load_account(db: Session, account_id: int) -> AccountPoolAccount | None:
    stmt = (
        select(AccountPoolAccount)
        .options(selectinload(AccountPoolAccount.project_memberships))
        .where(AccountPoolAccount.id == account_id)
    )
    return db.scalar(stmt)


@router.get("", response_model=list[AccountRead])
def list_accounts(
    project_id: int | None = None,
    status_filter: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[AccountPoolAccount]:
    require_role(ADMIN_ROLES)(current_user)
    stmt = select(AccountPoolAccount).options(selectinload(AccountPoolAccount.project_memberships)).order_by(AccountPoolAccount.id.desc())
    if project_id is not None:
        stmt = stmt.join(AccountProjectMembership, AccountProjectMembership.account_id == AccountPoolAccount.id).where(
            AccountProjectMembership.project_id == project_id
        )
    if status_filter is not None:
        stmt = stmt.where(AccountPoolAccount.status == status_filter)
    return list(db.scalars(stmt).all())


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> AccountPoolAccount:
    require_role(ADMIN_ROLES)(current_user)
    account = _load_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> AccountPoolAccount:
    require_role(ADMIN_ROLES)(current_user)
    duplicate = db.scalar(select(AccountPoolAccount).where(AccountPoolAccount.email == payload.email))
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account email already exists")
    account = AccountPoolAccount(
        name=payload.name,
        email=payload.email,
        provider=payload.provider,
        status=payload.status,
        remark=payload.remark,
        extra_json=payload.extra_json,
        login_secret_encrypted=encrypt_secret(payload.login_secret) if payload.login_secret else None,
        created_by=current_user.id,
    )
    db.add(account)
    db.flush()
    for project_id in payload.project_ids:
        if not db.get(Project, project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {project_id} not found")
        db.add(AccountProjectMembership(account_id=account.id, project_id=project_id))
    record_audit(db, user_id=current_user.id, action="account.create", target_type="account", target_id=account.id, summary=f"Created account {account.email}")
    db.commit()
    return _load_account(db, account.id)


@router.put("/{account_id}", response_model=AccountRead)
def update_account(account_id: int, payload: AccountUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> AccountPoolAccount:
    require_role(ADMIN_ROLES)(current_user)
    account = _load_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    for field in ["name", "email", "provider", "status", "remark"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(account, field, value)
    if payload.extra_json is not None:
        account.extra_json = payload.extra_json
    if payload.login_secret is not None:
        account.login_secret_encrypted = encrypt_secret(payload.login_secret)
    if payload.project_ids is not None:
        existing = {m.project_id: m for m in account.project_memberships}
        desired = set(payload.project_ids)
        for membership in list(account.project_memberships):
            if membership.project_id not in desired:
                db.delete(membership)
        for project_id in desired:
            if project_id not in existing:
                db.add(AccountProjectMembership(account_id=account.id, project_id=project_id))
    record_audit(db, user_id=current_user.id, action="account.update", target_type="account", target_id=account.id, summary=f"Updated account {account.email}")
    db.commit()
    return _load_account(db, account.id)


@router.post("/sync", response_model=list[AccountRead])
def sync_accounts(payload: AccountSyncRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> list[AccountPoolAccount]:
    require_role(ADMIN_ROLES)(current_user)
    created_ids: list[int] = []
    accounts = payload.accounts or [
        AccountCreate(name="浏览器同步账号", email=f"synced_{int(datetime.now(timezone.utc).timestamp())}@example.com", remark="从浏览器自动同步")
    ]
    for item in accounts:
        duplicate = db.scalar(select(AccountPoolAccount).where(AccountPoolAccount.email == item.email))
        if duplicate:
            duplicate.last_check_at = datetime.now(timezone.utc)
            continue
        account = AccountPoolAccount(
            name=item.name,
            email=item.email,
            provider=item.provider,
            status=item.status,
            remark=item.remark,
            extra_json=item.extra_json,
            login_secret_encrypted=encrypt_secret(item.login_secret) if item.login_secret else None,
            created_by=current_user.id,
            last_check_at=datetime.now(timezone.utc),
        )
        db.add(account)
        db.flush()
        for project_id in item.project_ids:
            db.add(AccountProjectMembership(account_id=account.id, project_id=project_id))
        created_ids.append(account.id)
    record_audit(db, user_id=current_user.id, action="account.sync", target_type="account", summary="Synced account pool", payload_json={"count": len(accounts)})
    db.commit()
    stmt = select(AccountPoolAccount).options(selectinload(AccountPoolAccount.project_memberships)).order_by(AccountPoolAccount.id.desc())
    if created_ids:
        stmt = stmt.where(AccountPoolAccount.id.in_(created_ids))
    return list(db.scalars(stmt).all())


@router.post("/{account_id}/verify", response_model=AccountRead)
def verify_account(account_id: int, payload: AccountVerifyRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> AccountPoolAccount:
    require_role(ADMIN_ROLES)(current_user)
    account = _load_account(db, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    account.last_check_at = datetime.now(timezone.utc)
    if payload.status is not None:
        account.status = payload.status
    if payload.remark is not None:
        account.remark = payload.remark
    record_audit(db, user_id=current_user.id, action="account.verify", target_type="account", target_id=account.id, summary=f"Verified account {account.email}")
    db.commit()
    return _load_account(db, account.id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(account_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    require_role(ADMIN_ROLES)(current_user)
    account = db.get(AccountPoolAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    record_audit(db, user_id=current_user.id, action="account.delete", target_type="account", target_id=account.id, summary=f"Deleted account {account.email}")
    db.delete(account)
    db.commit()
