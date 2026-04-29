from app.core.database import Base, engine
from app.models import (  # noqa: F401
    Annotation,
    AnnotationAttachment,
    Asset,
    AssetAttachment,
    AsyncJob,
    BankMaterial,
    BankReference,
    Episode,
    Notification,
    Project,
    Reference,
    ReviewRecord,
    Scene,
    SceneAssignment,
    SceneGroup,
    StageProgress,
    User,
    UserProjectMembership,
)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
