from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    CurrentUser,
    PRODUCER_ROLES,
    PROJECT_VISIBILITY_VALUES,
    require_project_access,
    require_project_settings_access,
    require_role,
)
from app.core.database import get_db
from app.models.admin import AuditLog
from app.models.project import Project, UserProjectMembership
from app.schemas.project import ProjectCreate, ProjectMemberWrite, ProjectRead, ProjectUpdate
from app.services.audit_service import record_audit

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

    membership_subquery = select(UserProjectMembership.project_id).where(UserProjectMembership.user_id == current_user.id)
    stmt = select(Project).options(selectinload(Project.memberships))
    if current_user.role == "producer":
        stmt = stmt.where(or_(Project.id.in_(membership_subquery), Project.visibility == "public"))
    else:
        stmt = stmt.where(Project.id.in_(membership_subquery))
    stmt = stmt.order_by(Project.id.desc())
    return list(db.scalars(stmt).all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Project:
    require_role(PRODUCER_ROLES)(current_user)
    visibility = (payload.visibility or "private").lower()
    if visibility not in PROJECT_VISIBILITY_VALUES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid project visibility")
    project = Project(
        name=payload.name,
        description=payload.description,
        project_type=payload.project_type,
        status=payload.status,
        visibility=visibility,
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
    for member_id in payload.member_ids:
        if member_id != current_user.id:
            db.add(
                UserProjectMembership(
                    user_id=member_id,
                    project_id=project.id,
                    role_in_project=None,
                )
            )
    record_audit(
        db,
        user_id=current_user.id,
        action="project.create",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        summary=f"Created project {project.name}",
    )
    db.commit()
    stmt = select(Project).options(selectinload(Project.memberships)).where(Project.id == project.id)
    return db.scalar(stmt)


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
    project = db.get(Project, project_id)
    require_project_settings_access(project, current_user)
    if payload.name is not None:
        project.name = payload.name
    if payload.description is not None:
        project.description = payload.description
    if payload.project_type is not None:
        project.project_type = payload.project_type
    if payload.status is not None:
        project.status = payload.status
    if payload.visibility is not None:
        visibility = payload.visibility.lower()
        if visibility not in PROJECT_VISIBILITY_VALUES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid project visibility")
        project.visibility = visibility
    if payload.deadline_at is not None:
        project.deadline_at = payload.deadline_at
    if payload.member_ids is not None:
        existing = {item.user_id for item in project.memberships}
        desired = set(payload.member_ids)
        for membership in list(project.memberships):
            if membership.user_id not in desired and membership.user_id != project.created_by:
                db.delete(membership)
        for user_id in desired:
            if user_id not in existing:
                db.add(UserProjectMembership(user_id=user_id, project_id=project.id))
    record_audit(
        db,
        user_id=current_user.id,
        action="project.update",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        summary=f"Updated project {project.name}",
    )
    db.commit()
    stmt = select(Project).options(selectinload(Project.memberships)).where(Project.id == project.id)
    return db.scalar(stmt)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    require_project_access(project_id, current_user, db)
    project = db.get(Project, project_id)
    require_project_settings_access(project, current_user)
    has_audit_history = db.scalar(select(AuditLog.id).where(AuditLog.project_id == project_id).limit(1))
    if has_audit_history:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="项目已有审计历史，不能直接删除，请改为归档",
        )
    record_audit(
        db,
        user_id=current_user.id,
        action="project.delete",
        target_type="project",
        target_id=project.id,
        project_id=project.id,
        summary=f"Deleted project {project.name}",
    )
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


@router.post("/{project_id}/members", response_model=ProjectRead)
def add_project_member(
    project_id: int,
    payload: ProjectMemberWrite,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Project:
    require_project_access(project_id, current_user, db)
    stmt = select(Project).options(selectinload(Project.memberships)).where(Project.id == project_id)
    project = db.scalar(stmt)
    require_project_settings_access(project, current_user)
    duplicate = next((m for m in project.memberships if m.user_id == payload.user_id), None)
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Member already exists")
    db.add(
        UserProjectMembership(
            user_id=payload.user_id,
            project_id=project_id,
            role_in_project=payload.role_in_project,
        )
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="project.member_add",
        target_type="project",
        target_id=project_id,
        project_id=project_id,
        summary=f"Added user {payload.user_id} to project {project_id}",
    )
    db.commit()
    return db.scalar(stmt)


@router.put("/{project_id}/members/{user_id}", response_model=ProjectRead)
def update_project_member(
    project_id: int,
    user_id: int,
    payload: ProjectMemberWrite,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Project:
    require_project_access(project_id, current_user, db)
    stmt = select(Project).options(selectinload(Project.memberships)).where(Project.id == project_id)
    project = db.scalar(stmt)
    require_project_settings_access(project, current_user)
    membership = next((m for m in project.memberships if m.user_id == user_id), None)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    membership.role_in_project = payload.role_in_project
    record_audit(
        db,
        user_id=current_user.id,
        action="project.member_update",
        target_type="project",
        target_id=project_id,
        project_id=project_id,
        summary=f"Updated member {user_id} in project {project_id}",
    )
    db.commit()
    return db.scalar(stmt)


@router.delete("/{project_id}/members/{user_id}", response_model=ProjectRead)
def remove_project_member(
    project_id: int,
    user_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Project:
    require_project_access(project_id, current_user, db)
    stmt = select(Project).options(selectinload(Project.memberships)).where(Project.id == project_id)
    project = db.scalar(stmt)
    require_project_settings_access(project, current_user)
    membership = next((m for m in project.memberships if m.user_id == user_id), None)
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    db.delete(membership)
    record_audit(
        db,
        user_id=current_user.id,
        action="project.member_remove",
        target_type="project",
        target_id=project_id,
        project_id=project_id,
        summary=f"Removed member {user_id} from project {project_id}",
    )
    db.commit()
    return db.scalar(stmt)
