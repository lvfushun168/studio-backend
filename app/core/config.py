from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "studio_asset_system Backend"
    app_env: str = "development"
    app_debug: bool = True
    database_url: str = "postgresql+psycopg://lvfushun@127.0.0.1:5432/studio_asset_system"
    media_root: str = "./storage"
    cookie_encryption_key: str = ""
    default_model: str | None = None
    dev_default_user_id: int | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def media_root_path(self) -> Path:
        return Path(self.media_root).resolve()


settings = Settings()
