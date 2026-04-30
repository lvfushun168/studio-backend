from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, DIRECTOR_PRODUCER_ROLES, get_accessible_project_ids, require_project_access, require_role
from app.core.database import get_db
from app.models.project import Episode
from app.schemas.episode import EpisodeCreate, EpisodeRead

router = APIRouter()


@router.get("", response_model=list[EpisodeRead])
def list_episodes(
    project_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Episode]:
    stmt = select(Episode).order_by(Episode.episode_number)
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(Episode.project_id == project_id)
    elif current_user.role != "admin":
        accessible_project_ids = get_accessible_project_ids(current_user, db)
        if not accessible_project_ids:
            return []
        stmt = stmt.where(Episode.project_id.in_(accessible_project_ids))
    return list(db.scalars(stmt).all())


@router.post("", response_model=EpisodeRead, status_code=status.HTTP_201_CREATED)
def create_episode(
    payload: EpisodeCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Episode:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(payload.project_id, current_user, db)
    episode = Episode(
        project_id=payload.project_id,
        episode_number=payload.episode_number,
        name=payload.name,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    return episode


@router.get("/{episode_id}", response_model=EpisodeRead)
def get_episode(
    episode_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Episode:
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(episode.project_id, current_user, db)
    return episode


@router.put("/{episode_id}", response_model=EpisodeRead)
def update_episode(
    episode_id: int,
    payload: EpisodeCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Episode:
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    require_project_access(episode.project_id, current_user, db)
    episode.episode_number = payload.episode_number
    episode.name = payload.name
    db.commit()
    db.refresh(episode)
    return episode


@router.delete("/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(
    episode_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    episode = db.get(Episode, episode_id)
    if not episode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(episode.project_id, current_user, db)
    db.delete(episode)
    db.commit()
