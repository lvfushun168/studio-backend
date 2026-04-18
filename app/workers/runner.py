from pathlib import Path

from sqlalchemy.orm import Session

from app.services.gemini_gateway import GeminiGateway
from app.services.storage_service import StorageService
from app.services.task_service import TaskService


class WorkerRunner:
    def __init__(self, db: Session):
        self.db = db
        self.tasks = TaskService(db)
        self.gateway = GeminiGateway()
        self.storage = StorageService()

    async def run_once(self) -> bool:
        task = self.tasks.claim_next_task()
        if not task:
            return False

        account = task.account
        if not account:
            self.tasks.mark_failed(task, "Task claimed without account.")
            return True

        try:
            output_paths = await self.gateway.generate_images(
                account=account,
                prompt=task.prompt,
                input_paths=[item.file_path for item in task.inputs],
                out_dir=self.storage.task_output_dir(task.task_no),
                model_name=task.model_name,
            )
            self.tasks.mark_success(task, output_paths)
        except Exception as exc:
            self.tasks.mark_failed(task, str(exc))

        return True
