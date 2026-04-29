from fastapi import APIRouter

from app.core.config import settings
from app.domains.stage_templates import STAGE_TEMPLATES
from app.schemas.system import BootstrapRead, StageTemplateItem


router = APIRouter()


@router.get("/bootstrap", response_model=BootstrapRead)
def get_bootstrap() -> BootstrapRead:
    stage_templates = {
        key: [StageTemplateItem(**item) for item in items]
        for key, items in STAGE_TEMPLATES.items()
    }
    return BootstrapRead(app_name=settings.app_name, stage_templates=stage_templates)
