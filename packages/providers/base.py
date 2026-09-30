"""Provider adapters (Doc 01): substitutable implementations.

A provider never receives raw credentials beyond its own bounded config, and
external content entering through a provider is untrusted data (Doc 08).
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderAdapter(Protocol):
    """Minimal contract: a provider executes a capability and returns a dict
    payload. Same contract across providers — swap requires benchmark +
    regression + approval (Doc 17 §9); the registry decides, not the caller."""

    key: str

    def call(self, capability_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class FailingProvider:
    """Test/dev provider that always errors — used to exercise fallback paths."""

    key: str = "failing"
    attempts: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def call(self, capability_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.attempts.append((capability_key, payload))
        raise RuntimeError("provider unavailable")


@dataclass
class EchoProvider:
    """Deterministic stub: echoes the payload back. Registered only in tests/dev."""

    key: str = "echo"
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def call(self, capability_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((capability_key, payload))
        return {"echoed": payload, "provider": self.key}
