from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.account import (
    AccountCreate,
    AccountListItem,
    AccountRead,
    AccountVerifyResult,
    BrowserImportResult,
)
from app.services.account_service import AccountService


router = APIRouter()


@router.get("", response_model=list[AccountListItem])
def list_accounts(db: Session = Depends(get_db)) -> list[AccountListItem]:
    return AccountService(db).list_accounts()


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreate, db: Session = Depends(get_db)) -> AccountRead:
    return AccountService(db).create_account(payload)


@router.post("/import-browser", response_model=BrowserImportResult)
async def import_browser_accounts(db: Session = Depends(get_db)) -> BrowserImportResult:
    service = AccountService(db)
    try:
        accounts = await service.import_accounts_from_browser()
        return BrowserImportResult(imported=len(accounts), accounts=accounts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{account_id}/verify", response_model=AccountVerifyResult)
async def verify_account(account_id: int, db: Session = Depends(get_db)) -> AccountVerifyResult:
    service = AccountService(db)
    try:
        account = service.get_account_or_404(account_id)
        return await service.verify_account(account)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
