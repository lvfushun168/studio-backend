from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    CurrentUser,
    require_project_access,
    DIRECTOR_PRODUCER_ROLES,
    require_role,
)
from app.core.database import get_db
from app.models.project import Project, UserProjectMembership
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()


@router.get("", response_model=list[ProjectRead])
def list_projects(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[Project]:
    """List projects the current user has access to."""
    if current_user.role == "admin":
        stmt = select(Project).options(selectinload(Project.memberships)).order_by(Project.id.desc())
        return list(db.scalars(stmt).all())

    stmt = (
        select(Project)
        .options(selectinload(Project.memberships))
        .join(UserProjectMembership, UserProjectMembership.project_id == Project.id)
        .where(UserProjectMembership.user_id == current_user.id)
        .order_by(Project.id.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Project:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    project = Project(
        name=payload.name,
        description=payload.description,
        project_type=payload.project_type,
        status=payload.status,
        deadline_at=payload.deadline_at,
        created_by=current_user.id,
    )
    db.add(project)
    db.flush()
    db.add(
        UserProjectMembership(
            user_id=current_user.id,
            project_id=project.id,
            role_in_project=current_user.role,
        )
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Project:
    require_project_access(project_id, current_user, db)
    stmt = select(Project).options(selectinload(Project.memberships)).where(Project.id == project_id)
    project = db.scalar(stmt)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Project:
    require_project_access(project_id, current_user, db)
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.project_type is not None:
        project.project_type = payload.project_type
    if payload.status is not None:
        project.status = payload.status
    if payload.deadline_at is not None:
        project.deadline_at = payload.deadline_at
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    require_project_access(project_id, current_user, db)
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    db.delete(project)
    db.commit()


@router.get("/{project_id}/members")
def list_project_members(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[dict]:
    require_project_access(project_id, current_user, db)
    stmt = select(UserProjectMembership).where(UserProjectMembership.project_id == project_id)
    memberships = db.scalars(stmt).all()
    return [{"user_id": m.user_id, "role_in_project": m.role_in_project} for m in memberships]
