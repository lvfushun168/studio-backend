from fastapi import APIRouter

from app.api.routes import accounts, health, tasks


api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(accounts.router, prefix="/accounts", tags=["accounts"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
