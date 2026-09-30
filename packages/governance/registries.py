"""Registries (Doc 17 steps 9-10; Doc 00 §24).

Provider Registry and Capability Registry. Capabilities declare which
profiles may call them (`allowed_profiles`, profile keys; NULL/empty = all),
their quota config, and their provider + fallback. Registration and health
changes are explicit operations; resolution fails closed.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.domain.enums import HealthState
from packages.domain.models import Capability, Provider


class RegistryError(Exception):
    pass


class ProviderRegistry:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register(
        self,
        key: str,
        name: str | None = None,
        version: str | None = None,
        privacy: dict[str, Any] | None = None,
        license: str | None = None,
        config: dict[str, Any] | None = None,
        health: str = HealthState.UNAVAILABLE.value,
    ) -> Provider:
        """Registers or updates a provider (config must be secret-free, Doc 08)."""
        provider = self.session.scalar(select(Provider).where(Provider.key == key))
        if provider is None:
            provider = Provider(key=key)
            self.session.add(provider)
        provider.name = name if name is not None else provider.name
        provider.version = version if version is not None else provider.version
        provider.privacy = privacy if privacy is not None else provider.privacy
        provider.license = license if license is not None else provider.license
        provider.config = config if config is not None else provider.config
        provider.health = health
        provider.status = "ACTIVE"
        provider.last_verified_at = datetime.now(UTC)
        self.session.flush()
        return provider

    def get(self, provider_id: UUID | None) -> Provider | None:
        if provider_id is None:
            return None
        return self.session.get(Provider, provider_id)

    def get_by_key(self, key: str) -> Provider | None:
        return self.session.scalar(select(Provider).where(Provider.key == key))

    def set_health(self, provider_id: UUID, health: HealthState) -> None:
        provider = self.session.get(Provider, provider_id)
        if provider is None:
            raise RegistryError("provider not found")
        provider.health = health.value
        self.session.flush()


class CapabilityRegistry:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register(
        self,
        key: str,
        provider_id: UUID | None = None,
        fallback_provider_id: UUID | None = None,
        version: str | None = None,
        schema: dict[str, Any] | None = None,
        quota: dict[str, Any] | None = None,
        cost: dict[str, Any] | None = None,
        allowed_profiles: list[str] | None = None,
    ) -> Capability:
        """Registers or updates a capability. allowed_profiles=None clears
        restriction (all profiles); an explicit list restricts by profile key."""
        cap = self.session.scalar(select(Capability).where(Capability.key == key))
        if cap is None:
            cap = Capability(key=key)
            self.session.add(cap)
        cap.provider_id = provider_id if provider_id is not None else cap.provider_id
        cap.fallback_provider_id = (
            fallback_provider_id if fallback_provider_id is not None else cap.fallback_provider_id
        )
        cap.version = version if version is not None else cap.version
        cap.schema_ = schema if schema is not None else cap.schema_
        cap.quota = quota if quota is not None else cap.quota
        cap.cost = cost if cost is not None else cap.cost
        cap.allowed_profiles = allowed_profiles
        cap.status = "ACTIVE"
        cap.last_verified_at = datetime.now(UTC)
        self.session.flush()
        return cap

    def get_by_key(self, key: str) -> Capability | None:
        return self.session.scalar(select(Capability).where(Capability.key == key))

    def list_all(self) -> list[Capability]:
        return list(self.session.scalars(select(Capability).order_by(Capability.key)))
