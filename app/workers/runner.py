from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.async_job import AsyncJob
from app.services.job_service import handle_job


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

        try:
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            self.db.flush()
            result = handle_job(self.db, job)
            job.status = "success"
            job.result_json = result
            job.finished_at = datetime.now(timezone.utc)
            self.db.add(job)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            job = self.db.get(AsyncJob, job.id)
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            if job.retry_count < job.max_retries:
                job.retry_count += 1
                job.status = "pending"
            else:
                job.status = "failed"
            self.db.add(job)
            self.db.commit()
        return True
