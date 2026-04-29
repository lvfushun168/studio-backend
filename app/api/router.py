from fastapi import APIRouter

from app.api.routes import health, projects, scenes, system


api_router = APIRouter(prefix="/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(scenes.router, prefix="/scenes", tags=["scenes"])
