from fastapi import APIRouter

from app.api.routes import (
    annotations,
    assets,
    bank,
    episodes,
    health,
    notifications,
    progress,
    projects,
    references,
    scene_groups,
    scenes,
    system,
    upload,
    users,
    workflow,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(episodes.router, prefix="/episodes", tags=["episodes"])
api_router.include_router(scene_groups.router, prefix="/scene-groups", tags=["scene-groups"])
api_router.include_router(scenes.router, prefix="/scenes", tags=["scenes"])
api_router.include_router(workflow.router, prefix="/workflow", tags=["workflow"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(annotations.router, prefix="/annotations", tags=["annotations"])
api_router.include_router(bank.router, prefix="/bank", tags=["bank"])
api_router.include_router(references.router, prefix="/references", tags=["references"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(progress.router, prefix="/progress", tags=["progress"])
