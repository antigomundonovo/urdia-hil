"""Runtime health checks and bootstrap validation (Doc 07)."""

from __future__ import annotations

from sqlalchemy import create_engine, text

from packages.shared.settings import get_settings


def main() -> int:
    settings = get_settings()
    url = settings.effective_database_url
    print(f"APP_ENV={settings.app_env}")
    print(f"DATABASE_URL={settings.redacted_database_url}")
    print(f"API={settings.api_host}:{settings.api_port}")

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
