"""URDIA BRAIN — skill layer (AMENDMENT-2026-10-01-012).

Skills are NARROW, contract-bound wrappers around existing handlers and
services — zero duplicated logic. The Brain is a DETERMINISTIC recipe
executor: it selects skills declared in reviewed code, never an LLM
freely deciding (LLM selection requires benchmark + approval, Doc 17 §9).

Guarantees:
- every skill declares its input contract and is validated before invoke;
- skills run with the caller's ExecutionContext (workspace/profile scoped);
- no skill crosses QC/approval/publication — the publisher_gate and the
  human confirm (Amendment 007) remain the only path to PUBLISHED.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from packages.shared.execution_context import ExecutionContext


class SkillError(Exception):
    """Skill prerequisites unmet (missing key, invalid payload, not ready)."""


@dataclass
class NullProgress:
    """Duck-typed JobProgress stand-in for out-of-band skill invocation."""

    completed: list[str] = field(default_factory=list)
    next_step: str | None = None

    def done(self, step: str) -> None:
        if step not in self.completed:
            self.completed.append(step)

    def next(self, step: str) -> None:
        self.next_step = step


@dataclass(frozen=True)
class SkillDefinition:
    key: str
    name: str
    description: str
    required_payload_keys: tuple[str, ...]
    invoke: Callable[[ExecutionContext, dict[str, Any]], dict[str, Any]]
    optional_payload_keys: tuple[str, ...] = ()
    status: str = "ACTIVE"  # or DECLARED (documented, not implemented)

    def validate_payload(self, payload: dict[str, Any]) -> None:
        missing = [k for k in self.required_payload_keys if k not in payload]
        if missing:
            raise SkillError(
                f"skill {self.key}: missing required payload keys: {missing}"
            )


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        if skill.key in self._skills:
            raise SkillError(f"skill already registered: {skill.key}")
        self._skills[skill.key] = skill

    def get(self, key: str) -> SkillDefinition:
        try:
            return self._skills[key]
        except KeyError as exc:
            raise SkillError(f"skill is not registered: {key}") from exc

    def keys(self) -> list[str]:
        return sorted(self._skills)
