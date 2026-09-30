"""FastAPI foundation (Doc 07): GET /api/v1/health with DB connectivity check.

Bound to 127.0.0.1 (Doc 08 — local initial binding). CORS is allowlist-based
and added when the web app lands; never a wildcard for authenticated endpoints.
"""

from fastapi import FastAPI

from apps.api.registry_routes import router as registry_router
from packages.domain.enums import HealthState
from packages.shared.db import engine
from packages.shared.settings import get_settings

app = FastAPI(title="URDIA HIL API", version="0.3.0", docs_url="/api/docs")
app.include_router(registry_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    settings = get_settings()
    state = HealthState.HEALTHY
    detail = {}
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:
        state = HealthState.DEGRADED
        detail["database"] = HealthState.UNAVAILABLE.value
    return {"status": state.value, "app_env": settings.app_env, **detail}
