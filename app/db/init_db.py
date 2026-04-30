def init_db() -> None:
    """Deprecated helper kept for compatibility.

    Database schema must be initialized via Alembic migrations instead of
    implicit metadata.create_all().
    """
    return None
