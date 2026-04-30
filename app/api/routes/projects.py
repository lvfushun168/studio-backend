from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    stmt = select(Project).order_by(Project.id.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(
        name=payload.name,
        description=payload.description,
        project_type=payload.project_type,
        status=payload.status,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)) -> Project:
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
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    db.delete(project)
    db.commit()
