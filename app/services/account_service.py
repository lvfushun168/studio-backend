import hashlib
import re
from datetime import datetime

from curl_cffi.requests import AsyncSession, Cookies
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret
from app.models.account import Account
from app.schemas.account import AccountCreate, AccountVerifyResult

from gemini_webapi.utils.load_browser_cookies import load_browser_cookies


EMAIL_RE = re.compile(r'"oPEP7c":"([^"]+)"')
ACCOUNT_ID_RE = re.compile(r'"qDCSke":"([^"]+)"')


class AccountService:
    def __init__(self, db: Session):
        self.db = db

    def list_accounts(self) -> list[Account]:
        return list(self.db.scalars(select(Account).order_by(Account.id.desc())).all())

    def create_account(self, payload: AccountCreate) -> Account:
        account = Account(
            name=payload.name,
            email=payload.email,
            account_id=payload.account_id,
            model_hint=payload.model_hint,
            secure_1psid_enc=encrypt_secret(payload.secure_1psid),
            secure_1psidts_enc=encrypt_secret(payload.secure_1psidts) if payload.secure_1psidts else None,
            notes=payload.notes,
        )
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return account

    async def import_accounts_from_browser(self) -> list[Account]:
        browser_map = load_browser_cookies(domain_name="google.com", verbose=True)
        if not browser_map:
            raise ValueError("No browser cookies were found on this machine.")

        imported_accounts: list[Account] = []
        for browser, cookie_list in browser_map.items():
            cookie_values = {item["name"]: item["value"] for item in cookie_list}
            secure_1psid = cookie_values.get("__Secure-1PSID")
            secure_1psidts = cookie_values.get("__Secure-1PSIDTS")
            if not secure_1psid:
                continue

            email, account_id = await self._fetch_identity(secure_1psid, secure_1psidts)
            account = self._find_existing_account(secure_1psid, email, account_id)
            if not account:
                account = Account(
                    name=email or f"{browser}-imported",
                    email=email,
                    account_id=account_id,
                    model_hint="gemini-3-pro",
                    secure_1psid_enc=encrypt_secret(secure_1psid),
                    secure_1psidts_enc=encrypt_secret(secure_1psidts) if secure_1psidts else None,
                    notes=f"Imported from browser: {browser}",
                    last_verified_at=datetime.utcnow(),
                )
                self.db.add(account)
            else:
                account.email = email or account.email
                account.account_id = account_id or account.account_id
                account.secure_1psid_enc = encrypt_secret(secure_1psid)
                account.secure_1psidts_enc = encrypt_secret(secure_1psidts) if secure_1psidts else None
                account.last_verified_at = datetime.utcnow()
                if not account.notes:
                    account.notes = f"Imported from browser: {browser}"
                self.db.add(account)

            self.db.flush()
            imported_accounts.append(account)

        if not imported_accounts:
            raise ValueError("No Gemini-capable browser cookie session was found.")

        self.db.commit()
        for account in imported_accounts:
            self.db.refresh(account)
        return imported_accounts

    def get_account_or_404(self, account_id: int) -> Account:
        account = self.db.get(Account, account_id)
        if not account:
            raise ValueError("Account not found")
        return account

    async def verify_account(self, account: Account) -> AccountVerifyResult:
        secure_1psid = decrypt_secret(account.secure_1psid_enc)
        secure_1psidts = decrypt_secret(account.secure_1psidts_enc)
        if not secure_1psid:
            raise ValueError("Account is missing __Secure-1PSID")

        email, account_id = await self._fetch_identity(secure_1psid, secure_1psidts)
        account.email = email or account.email
        account.account_id = account_id or account.account_id
        account.last_verified_at = datetime.utcnow()
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)

        return AccountVerifyResult(
            ok=True,
            email=account.email,
            account_id=account.account_id,
            status=account.status.value,
            psid_hash=hashlib.sha256(secure_1psid.encode("utf-8")).hexdigest()[:12],
        )

    def _find_existing_account(
        self,
        secure_1psid: str,
        email: str | None,
        account_id: str | None,
    ) -> Account | None:
        for account in self.list_accounts():
            saved_psid = decrypt_secret(account.secure_1psid_enc)
            if saved_psid and saved_psid == secure_1psid:
                return account
            if email and account.email == email:
                return account
            if account_id and account.account_id == account_id:
                return account
        return None

    async def _fetch_identity(
        self,
        secure_1psid: str,
        secure_1psidts: str | None,
    ) -> tuple[str | None, str | None]:
        jar = Cookies()
        jar.set("__Secure-1PSID", secure_1psid, domain=".google.com", path="/")
        if secure_1psidts:
            jar.set("__Secure-1PSIDTS", secure_1psidts, domain=".google.com", path="/")

        session = AsyncSession(impersonate="chrome", allow_redirects=True, cookies=jar)
        try:
            response = await session.get("https://gemini.google.com/app")
            response.raise_for_status()
            text = response.text
            email_match = EMAIL_RE.search(text)
            account_id_match = ACCOUNT_ID_RE.search(text)
            email = email_match.group(1) if email_match else None
            account_id = account_id_match.group(1) if account_id_match else None
            return email, account_id
        finally:
            await session.close()
