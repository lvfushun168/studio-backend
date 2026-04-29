from fastapi import APIRouter

from app.core.config import settings
from app.schemas.system import HealthRead


router = APIRouter()


@router.get("/health", response_model=HealthRead)
def healthcheck() -> HealthRead:
    return HealthRead(status="ok", app=settings.app_name, env=settings.app_env)
