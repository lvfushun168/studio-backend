import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


def _build_fernet() -> Fernet:
    seed = settings.cookie_encryption_key or "dev-only-cookie-key-change-me"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


fernet = _build_fernet()


def encrypt_secret(value: str) -> str:
    return fernet.encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
