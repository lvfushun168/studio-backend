from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.system import HealthDependencyRead, HealthRead


router = APIRouter()


@router.get("/health", response_model=HealthRead)
def healthcheck(db: Session = Depends(get_db)) -> HealthRead:
    db_ok = True
    db_detail = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_ok = False
        db_detail = str(exc)

    storage_ok = True
    storage_detail = "ok"
    try:
        probe_dir = settings.media_root_path / "_health"
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file = probe_dir / "probe.txt"
        probe_file.write_text("ok", encoding="utf-8")
        if probe_file.read_text(encoding="utf-8") != "ok":
            raise RuntimeError("storage read/write probe mismatch")
        probe_file.unlink(missing_ok=True)
    except Exception as exc:
        storage_ok = False
        storage_detail = str(exc)

    overall = "ok" if db_ok and storage_ok else "degraded"
    return HealthRead(
        status=overall,
        app=settings.app_name,
        env=settings.app_env,
        database=HealthDependencyRead(ok=db_ok, detail=db_detail),
        storage=HealthDependencyRead(ok=storage_ok, detail=storage_detail),
    )
