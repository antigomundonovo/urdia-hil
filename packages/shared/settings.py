"""Runtime settings (Doc 07 — Runtime + Installation + Operations).

Reads the environment / `.env`. Never stores secrets in code, prompts, logs
or frontend (Doc 08).
"""

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

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

    default_profile_key: str = "default"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_base_url: str = "http://localhost:5173"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str = Field(default="", repr=False)
    smtp_from_email: str | None = None
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False

    # LLM provider (Doc 17 §9/§15): key never logged/repr'd (Doc 08).
    google_ai_api_key: str = Field(default="", repr=False)
    # gemini-2.5-flash foi descontinuado para chaves novas (API, 2026-10);
    # default segue o modelo atual recomendado pela própria API.
    llm_model: str = "gemini-3.8-flash"
    llm_timeout_seconds: float = 60.0

    # Gateway OpenAI-compatível — provider de PRODUÇÃO para capacidades de
    # TEXTO desde 2026-10-04 (benchmark 7/7 + aprovação humana do dono,
    # Doc 17 §9). Valores: "gateway" | "gemini". Vision permanece no gemini.
    llm_provider: str = "gateway"
    llm_gateway_base_url: str = ""
    llm_gateway_api_key: str = Field(default="", repr=False)
    llm_gateway_model: str = "auto/gemini"
    llm_gateway_label: str = "gateway-omniroute"

    # YouTube adapter (AMENDMENT-012): YouTube requires a session for
    # metadata; cookies come from the operator's own browser (optional).
    yt_dlp_cookies_from_browser: str | None = None
    yt_dlp_cookies_file: str | None = None

    # Instagram live publishing (Doc 14 API method; credentials from the
    # Meta app "URDIA-Media - IG"). Secrets never repr'd/logged (Doc 08).
    meta_app_id: str = ""
    meta_app_secret: str = Field(default="", repr=False)
    meta_instagram_token: str = Field(default="", repr=False)
    meta_instagram_token_expires_at: str | None = None

    # TikTok Content Posting API. User access token is secret and never repr/logged.
    tiktok_client_key: str = ""
    tiktok_client_secret: str = Field(default="", repr=False)
    tiktok_access_token: str = Field(default="", repr=False)
    tiktok_open_id: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        """Doc 08: CORS por allowlist, nunca wildcard."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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

    @property
    def redacted_database_url(self) -> str:
        """Mask credentials before printing or logging runtime connection details."""
        parsed = urlsplit(self.effective_database_url)
        if not parsed.hostname or not parsed.password:
            return self.effective_database_url

        username = parsed.username or ""
        netloc = f"{username}:***@{parsed.hostname}"
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))

    def validation_issues(self) -> list[str]:
        """Return actionable configuration errors before a DB connection is attempted."""
        issues: list[str] = []
        if not self.postgres_password or self.postgres_password == "${POSTGRES_PASSWORD}":
            issues.append("POSTGRES_PASSWORD is missing or unresolved in .env")
        if self.database_url and "${" in self.database_url:
            issues.append("DATABASE_URL still contains an unresolved environment placeholder")
        return issues


@lru_cache
def get_settings() -> Settings:
    return Settings()
