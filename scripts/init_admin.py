#!/usr/bin/env python3
"""Create or update the bootstrap admin account."""

from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select

from app.core.auth import generate_api_key
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User


def main() -> None:
    username = os.getenv("STUDIO_ADMIN_USERNAME", "admin").strip() or "admin"
    password = os.getenv("STUDIO_ADMIN_PASSWORD", "admin123")
    display_name = os.getenv("STUDIO_ADMIN_DISPLAY_NAME", "Admin").strip() or "Admin"
    email = os.getenv("STUDIO_ADMIN_EMAIL", "admin@example.com").strip() or "admin@example.com"

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                display_name=display_name,
                email=email,
                role="admin",
                password_hash=hash_password(password),
                api_key=generate_api_key(),
                is_active=True,
            )
            db.add(user)
        else:
            user.display_name = display_name
            user.email = email
            user.role = "admin"
            user.password_hash = hash_password(password)
            user.is_active = True
            if not user.api_key:
                user.api_key = generate_api_key()
        db.commit()
        print(f"bootstrap admin ready: {username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
