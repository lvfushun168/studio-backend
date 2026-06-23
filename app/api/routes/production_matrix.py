from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, PRODUCER_ROLES, require_project_access, require_role
from app.core.database import get_db
from app.models.project import Project
from app.services.production_matrix_service import build_production_matrix


router = APIRouter()


@router.get("")
def get_production_matrix(
    project_id: int,
    current_user: CurrentUser,
    episode_id: int | None = None,
    scene_group_id: int | None = None,
    stage_key: str | None = None,
    assignee_id: int | None = None,
    work_step_status: list[str] | None = Query(default=None),
    overdue_only: bool = False,
    blocked_only: bool = False,
    unassigned_only: bool = False,
    priority: str | None = None,
    keyword: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    require_role(PRODUCER_ROLES)(current_user)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    require_project_access(project_id, current_user, db)
    return build_production_matrix(
        db,
        project_id=project_id,
        episode_id=episode_id,
        scene_group_id=scene_group_id,
        stage_key=stage_key,
        assignee_id=assignee_id,
        work_step_statuses=work_step_status,
        overdue_only=overdue_only,
        blocked_only=blocked_only,
        unassigned_only=unassigned_only,
        priority=priority,
        keyword=keyword,
    )
