"""ExecutionContext (Doc 01 — Repository + Service Architecture).

Toda operação relevante carrega workspace_id, profile_id e scope (Doc 00 §7).
"""

from uuid import UUID

from pydantic import BaseModel, Field


class ExecutionContext(BaseModel):
    workspace_id: UUID
    profile_id: UUID | None = None
    actor_id: UUID | None = None
    job_id: UUID | None = None
    capability: str | None = None
    correlation_id: str | None = Field(default=None, max_length=128)
