"""Pytest configuration for test_prd5_full.py."""
import pytest


@pytest.fixture
def shared_context():
    """Shared dict for test inter-communication."""
    return {}