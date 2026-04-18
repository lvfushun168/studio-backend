import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account, AccountStatus
from app.models.task import Task, TaskInput, TaskOutput, TaskStatus
from app.schemas.task import TaskCreate
from app.services.storage_service import StorageService


class TaskService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = StorageService()

    def list_tasks(self) -> list[Task]:
        stmt = (
            select(Task)
            .options(selectinload(Task.inputs), selectinload(Task.outputs), selectinload(Task.account))
            .order_by(Task.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def get_task(self, task_id: int) -> Task | None:
        stmt = (
            select(Task)
            .options(selectinload(Task.inputs), selectinload(Task.outputs), selectinload(Task.account))
            .where(Task.id == task_id)
        )
        return self.db.scalar(stmt)

    def create_task(self, payload: TaskCreate) -> Task:
        task_no = secrets.token_hex(8)
        stored_inputs = self.storage.persist_input_paths(task_no, payload.input_paths)
        return self._create_task_record(
            task_no=task_no,
            prompt=payload.prompt,
            mode=payload.mode,
            model_name=payload.model_name,
            image_count=payload.image_count,
            stored_inputs=stored_inputs,
        )

    def create_task_with_uploaded_files(
        self,
        prompt: str,
        mode: str,
        model_name: str | None,
        image_count: int,
        uploaded_files: list[tuple[str, bytes]],
    ) -> Task:
        task_no = secrets.token_hex(8)
        stored_inputs = self.storage.persist_uploaded_files(task_no, uploaded_files)
        return self._create_task_record(
            task_no=task_no,
            prompt=prompt,
            mode=mode,
            model_name=model_name,
            image_count=image_count,
            stored_inputs=stored_inputs,
        )

    def _create_task_record(
        self,
        task_no: str,
        prompt: str,
        mode: str,
        model_name: str | None,
        image_count: int,
        stored_inputs: list[str],
    ) -> Task:
        task = Task(
            task_no=task_no,
            prompt=prompt,
            mode=mode,
            model_name=model_name,
            image_count=image_count,
            status=TaskStatus.PENDING,
        )
        self.db.add(task)
        self.db.flush()

        for index, path in enumerate(stored_inputs):
            self.db.add(TaskInput(task_id=task.id, file_path=path, sort_order=index))

        self.db.commit()
        return self.get_task(task.id)

    def claim_next_task(self) -> Task | None:
        stmt = (
            select(Task)
            .options(selectinload(Task.inputs), selectinload(Task.outputs), selectinload(Task.account))
            .where(Task.status == TaskStatus.PENDING)
            .order_by(Task.id.asc())
        )
        task = self.db.scalar(stmt)
        if not task:
            return None

        account = self._pick_account()
        if not account:
            raise ValueError("No active account available.")

        task.account_id = account.id
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        account.last_used_at = datetime.utcnow()
        self.db.add_all([task, account])
        self.db.commit()
        return self.get_task(task.id)

    def mark_success(self, task: Task, output_paths: list[str]) -> Task:
        task.status = TaskStatus.SUCCESS
        task.finished_at = datetime.utcnow()
        task.error_message = None
        for path in output_paths:
            self.db.add(TaskOutput(task_id=task.id, file_path=path))

        if task.account_id:
            account = self.db.get(Account, task.account_id)
            if account:
                account.success_count += 1
                account.fail_count = 0
                self.db.add(account)

        self.db.add(task)
        self.db.commit()
        return self.get_task(task.id)

    def mark_failed(self, task: Task, error_message: str) -> Task:
        task.status = TaskStatus.FAILED
        task.finished_at = datetime.utcnow()
        task.error_message = error_message

        if task.account_id:
            account = self.db.get(Account, task.account_id)
            if account:
                account.fail_count += 1
                if account.fail_count >= 3:
                    account.status = AccountStatus.COOLDOWN
                self.db.add(account)

        self.db.add(task)
        self.db.commit()
        return self.get_task(task.id)

    def _pick_account(self) -> Account | None:
        stmt = (
            select(Account)
            .where(Account.status == AccountStatus.ACTIVE)
            .order_by(Account.last_used_at.asc().nullsfirst(), Account.id.asc())
        )
        return self.db.scalar(stmt)
