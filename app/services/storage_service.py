import shutil
from pathlib import Path

from app.core.config import settings


class StorageService:
    def __init__(self) -> None:
        self.root = settings.media_root_path
        self.root.mkdir(parents=True, exist_ok=True)

    def task_input_dir(self, task_no: str) -> Path:
        path = self.root / "tasks" / task_no / "inputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def task_output_dir(self, task_no: str) -> Path:
        path = self.root / "tasks" / task_no / "outputs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def persist_input_paths(self, task_no: str, input_paths: list[str]) -> list[str]:
        dest_dir = self.task_input_dir(task_no)
        stored: list[str] = []
        for original in input_paths:
            src = Path(original).expanduser().resolve()
            if not src.is_file():
                raise ValueError(f"Input file does not exist: {original}")
            dest = dest_dir / src.name
            shutil.copy2(src, dest)
            stored.append(str(dest))
        return stored

    def persist_uploaded_files(self, task_no: str, files: list[tuple[str, bytes]]) -> list[str]:
        dest_dir = self.task_input_dir(task_no)
        stored: list[str] = []
        for original_name, content in files:
            safe_name = Path(original_name).name or "upload.bin"
            dest = dest_dir / safe_name
            dest.write_bytes(content)
            stored.append(str(dest))
        return stored
