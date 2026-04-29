from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.async_job import AsyncJob


class WorkerRunner:
    def __init__(self, db: Session):
        self.db = db

    async def run_once(self) -> bool:
        stmt = (
            select(AsyncJob)
            .where(AsyncJob.status == "pending")
            .order_by(AsyncJob.priority.asc(), AsyncJob.id.asc())
        )
        job = self.db.scalar(stmt)
        if not job:
            return False

        job.status = "success"
        job.result_json = {"message": "No handler registered yet."}
        self.db.add(job)
        self.db.commit()
        return True
