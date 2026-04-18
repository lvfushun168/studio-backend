from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Gemini WebAPI Backend"
    app_env: str = "development"
    app_debug: bool = True
    database_url: str = "sqlite:///./app.db"
    media_root: str = "./storage"
    cookie_encryption_key: str = ""
    default_model: str = "gemini-3-pro"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def media_root_path(self) -> Path:
        return Path(self.media_root).resolve()


settings = Settings()
