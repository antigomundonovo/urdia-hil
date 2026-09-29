"""Generic Agent Input/Output contracts (Doc 02).

Validation pipeline for every agent output (Doc 05):
parse → schema validation → semantic validation → policy validation → persist.
External content is untrusted data and never becomes instruction (Doc 08).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class AgentExecution(BaseModel):
    model_config = ConfigDict(strict=True)

    job_id: str = ""
    workspace_id: str = ""
    profile_id: str = ""
    actor_id: str = ""
    correlation_id: str = ""


class AgentTask(BaseModel):
    type: str
    instructions: str = ""


class GenericAgentInput(BaseModel):
    model_config = ConfigDict(strict=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    execution: AgentExecution
    task: AgentTask
    context: dict[str, Any] = Field(default_factory=dict)
    allowed_capabilities: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class GenericAgentOutput(BaseModel):
    model_config = ConfigDict(strict=True)

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    status: Literal["OK", "ERROR"] = "OK"
    result: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recommended_next_action: str | None = None
