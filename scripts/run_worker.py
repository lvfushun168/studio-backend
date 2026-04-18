import asyncio

from app.core.database import SessionLocal
from app.db.init_db import init_db
from app.workers.runner import WorkerRunner


async def main() -> None:
    init_db()
    while True:
        db = SessionLocal()
        try:
            worked = await WorkerRunner(db).run_once()
        finally:
            db.close()

        if not worked:
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
