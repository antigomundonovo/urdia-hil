"""Provider-neutral contracts for platform integrations (Doc 14)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from packages.domain.enums import PlatformErrorKind, PublicationMethod


class PlatformAdapterError(RuntimeError):
    """Sanitized normalized failure; provider response details are not retained."""

    def __init__(self, kind: PlatformErrorKind) -> None:
        self.kind = kind
        super().__init__(kind.value)


@dataclass(frozen=True)
class PlatformDescriptor:
    key: str
    capabilities: tuple[str, ...]
    publication_method: PublicationMethod
    requirements: Mapping[str, Any]
    limits: Mapping[str, Any]
    quota: Mapping[str, Any]
    analytics: tuple[str, ...]
    status: str
    last_verified: datetime | None = None


class PlatformAdapter(Protocol):
    """Platform work stays behind replaceable adapters and opaque secret refs.

    Raise ``PlatformAdapterError`` so provider-specific failures are normalized
    without exposing response bodies or credentials.
    """

    descriptor: PlatformDescriptor

    def validate_payload(self, payload: dict[str, Any]) -> None:
        """Raise INVALID_PAYLOAD or POLICY_BLOCKED before any publish attempt."""
        ...

    def publish(
        self, payload: dict[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        """Return the provider's normalized publication result."""
        ...

    def collect_analytics(self, remote_id: str) -> dict[str, Any]:
        """Return normalized metric values for a remote publication."""
        ...

    def revoke_account(self, credential_ref: str) -> bool:
        """Revoke provider access when supported; never accept a raw token."""
        ...


class PlatformRegistry:
    """Explicit adapter registry; no platform is available until configured."""

    def __init__(self) -> None:
        self._adapters: dict[str, PlatformAdapter] = {}

    def register(self, adapter: PlatformAdapter) -> None:
        descriptor = adapter.descriptor
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", descriptor.key):
            raise ValueError("platform key must be a lowercase identifier")
        if descriptor.key in self._adapters:
            raise ValueError(f"platform adapter already registered: {descriptor.key}")
        self._adapters[descriptor.key] = adapter

    def get(self, key: str) -> PlatformAdapter:
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise LookupError(f"platform adapter is not configured: {key}") from exc

    def descriptors(self) -> tuple[PlatformDescriptor, ...]:
        return tuple(self._adapters[key].descriptor for key in sorted(self._adapters))


platform_registry = PlatformRegistry()
