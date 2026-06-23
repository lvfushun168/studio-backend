"""Shared pytest configuration."""
from pathlib import Path
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def enable_test_user_header(monkeypatch):
    """Enable the explicitly development-only identity header in tests.

    Production keeps ``ALLOW_X_USER_ID_AUTH=false``; the smoke suite uses the
    header to exercise role boundaries without sharing login sessions.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "allow_x_user_id_auth", True)


@pytest.fixture
def shared_context():
    """Shared dict for test inter-communication."""
    return {}
