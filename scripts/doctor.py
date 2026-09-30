"""Runtime health checks and bootstrap validation (Doc 07)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text

from packages.shared.settings import get_settings


def _env_status() -> str:
    env_file = Path(".env")
    if env_file.exists():
        return "READY"
    return "MISSING"


def main() -> int:
    settings = get_settings()
    url = settings.effective_database_url
    print(f"APP_ENV={settings.app_env}")
    print(f"ENV_FILE={_env_status()}")
    print(f"DATABASE_URL={settings.redacted_database_url}")
    print(f"API={settings.api_host}:{settings.api_port}")
    email_ready = bool(
        settings.smtp_host
        and settings.smtp_from_email
        and (settings.smtp_starttls or settings.smtp_use_ssl)
    )
    print(f"EMAIL_DELIVERY={'READY' if email_ready else 'NOT_CONFIGURED'}")

    issues = settings.validation_issues()
    if issues:
        print("ENV=INVALID")
        for issue in issues:
            print(f" - {issue}")
        return 2

    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised in runtime ops, not unit tests
        print(f"DATABASE=UNAVAILABLE: {exc}")
        return 1

    print("DATABASE=READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
