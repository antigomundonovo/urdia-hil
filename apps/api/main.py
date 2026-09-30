"""FastAPI foundation with local health, authentication, and scoped APIs."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.analytics_routes import router as analytics_router
from apps.api.auth import require_workspace_access
from apps.api.auth_routes import router as auth_router
from apps.api.content_routes import router as content_router
from apps.api.jobs_routes import router as jobs_router
from apps.api.opportunities_routes import router as opportunities_router
from apps.api.profiles_routes import router as profiles_router
from apps.api.registry_routes import router as registry_router
from apps.api.sources_routes import router as sources_router
from packages.domain.enums import HealthState
from packages.shared.db import engine
from packages.shared.settings import get_settings

app = FastAPI(title="URDIA HIL API", version="1.0.0", docs_url="/api/docs")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,  # explicit allowlist (Doc 08)
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.include_router(auth_router)
app.include_router(registry_router, dependencies=[Depends(require_workspace_access)])
app.include_router(jobs_router, dependencies=[Depends(require_workspace_access)])
app.include_router(profiles_router, dependencies=[Depends(require_workspace_access)])
app.include_router(opportunities_router, dependencies=[Depends(require_workspace_access)])
app.include_router(sources_router, dependencies=[Depends(require_workspace_access)])
app.include_router(content_router, dependencies=[Depends(require_workspace_access)])
app.include_router(analytics_router, dependencies=[Depends(require_workspace_access)])


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
