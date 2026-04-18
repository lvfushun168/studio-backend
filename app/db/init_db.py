from app.core.database import Base, engine
from app.models import account, task  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
