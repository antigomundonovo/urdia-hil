"""FastAPI foundation with local health, authentication, and scoped APIs."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.analytics_routes import router as analytics_router
from apps.api.audio_routes import router as audio_router
from apps.api.auth import require_workspace_access
from apps.api.auth_routes import router as auth_router
from apps.api.bridge_routes import router as bridge_router
from apps.api.content_routes import router as content_router
from apps.api.jobs_routes import router as jobs_router
from apps.api.memory_routes import router as memory_router
from apps.api.opportunities_routes import router as opportunities_router
from apps.api.profiles_routes import router as profiles_router
from apps.api.registry_routes import router as registry_router
from apps.api.social_routes import router as social_router
from apps.api.sources_routes import router as sources_router
from apps.api.tiktok_routes import router as tiktok_router
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
app.include_router(social_router, dependencies=[Depends(require_workspace_access)])
# Audio / Music Intelligence (Emenda 014): human session required; the
# human gate lives in the decision route itself.
app.include_router(audio_router, dependencies=[Depends(require_workspace_access)])
# Studio bridge: management routes authenticate the human session themselves;
# export routes authenticate the machine key themselves (allowlist = this
# router, Emenda 002).
app.include_router(bridge_router)
# Auxiliary memory: enforces workspace membership itself (workspace_id in body).
app.include_router(memory_router)
# TikTok connection flow: no session dependency — the OAuth landing uses
# the short-lived single-use authorization code as credential (local machine).
app.include_router(tiktok_router)


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
