"""Runtime settings (Doc 07 — Runtime + Installation + Operations).

Reads the environment / `.env`. Never stores secrets in code, prompts, logs
or frontend (Doc 08).
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    web_port: int = 5173

    postgres_user: str = "urdia"
    postgres_password: str = Field(default="", repr=False)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "urdia"
    database_url: str | None = None

    asset_root: str = "./assets"
    export_root: str = "./assets/exports"
    cache_root: str = "./assets/cache"
    temp_root: str = "./assets/temp"

    default_profile_key: str = "antigo_mundo_novo"
    log_level: str = "INFO"

    @property
    def effective_database_url(self) -> str:
        """DATABASE_URL wins when fully set; otherwise compose from parts.

        `.env.example` uses ``${POSTGRES_PASSWORD}`` inside DATABASE_URL — when
        that placeholder survives unresolved, fall back to composition so the
        app never connects with a literal ``${...}`` password.
        """
        if self.database_url and "${" not in self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
