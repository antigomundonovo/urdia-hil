"""Capability call pipeline (Doc 05):

    permission → profile → capability → provider → quota → execute → validate → audit

Fail-closed at every step (Doc 17 §8): unknown capability, inactive capability,
unhealthy provider, unauthorized profile or exhausted quota never execute.
Provider failure falls back to the capability's fallback provider with the
same contract, and every attempt is audited (Doc 16: fallback preserving
contract + audit). Prompt output is never governance: outputs must pass the
declared schema validator before being returned as OK.
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from packages.domain.enums import HealthState
from packages.domain.models import Capability, Profile, Provider
from packages.domain.repositories import AuditRepository
from packages.governance.audit import append_audit
from packages.governance.registries import CapabilityRegistry, ProviderRegistry
from packages.providers.base import ProviderAdapter
from packages.shared.execution_context import ExecutionContext


class CallStatus(StrEnum):
    OK = "OK"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    QUOTA_LIMITED = "QUOTA_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class CapabilityCallResult(BaseModel):
    status: CallStatus
    output: dict[str, Any] | None = None
    provider_used: str | None = None
    fallback_used: bool = False
    audit_id: UUID | None = None
    reason: str | None = None


class QuotaExceeded(Exception):
    pass


class CapabilityCaller:
    """Executes governed capability calls. Providers are injected by the
    composition root — the caller never touches credentials (Doc 08)."""

    def __init__(self, session: Session, providers: dict[str, ProviderAdapter]) -> None:
        self.session = session
        self.providers = providers
        self.provider_registry = ProviderRegistry(session)
        self.capability_registry = CapabilityRegistry(session)
        self.audit = AuditRepository(session)

    # --- steps -----------------------------------------------------------

    def _resolve_profile(self, ctx: ExecutionContext) -> Profile | None:
        if ctx.profile_id is None:
            return None
        profile = self.session.get(Profile, ctx.profile_id)
        if profile is None or profile.workspace_id != ctx.workspace_id:
            return None  # profile isolation: mismatch is treated as absent
        return profile

    def _profile_allowed(self, cap: Capability, profile: Profile | None) -> bool:
        allowed = cap.allowed_profiles
        if not allowed:  # NULL/empty → every profile (documented decision)
            return True
        if profile is None:
            return False
        return profile.key in allowed

    def _provider_callable(self, provider: Provider | None) -> bool:
        if provider is None:
            return False
        if provider.health in (HealthState.HEALTHY.value, HealthState.DEGRADED.value):
            return True
        return False  # fail closed on UNAVAILABLE/QUOTA_LIMITED/AUTH_ERROR/POLICY_BLOCKED

    def _check_quota(self, cap: Capability, ctx: ExecutionContext) -> None:
        quota = cap.quota or {}
        max_calls = quota.get("max_calls_per_day")
        if not max_calls:
            return
        since = datetime.now(UTC) - timedelta(days=1)
        used = self.audit.count_calls_since(cap.key, since, ctx.workspace_id)
        if used >= max_calls:
            raise QuotaExceeded(f"quota {used}/{max_calls} in the last 24h")

    def _execute(
        self, cap: Capability, payload: dict[str, Any]
    ) -> tuple[Any, str | None, bool]:
        """Try primary then fallback — both on health gate AND runtime failure
        (Doc 16: primary unavailable → fallback with same contract and audit).
        Returns (result, provider_key, fallback_used)."""
        primary_error: str | None = None
        primary = self.provider_registry.get(cap.provider_id)
        if self._provider_callable(primary):
            adapter = self.providers.get(primary.key)
            if adapter is not None:
                try:
                    return adapter.call(cap.key, payload), primary.key, False
                except Exception as exc:
                    primary_error = f"{primary.key}: {exc}"

        fallback = self.provider_registry.get(cap.fallback_provider_id)
        if self._provider_callable(fallback):
            adapter = self.providers.get(fallback.key)
            if adapter is not None:
                try:
                    return adapter.call(cap.key, payload), fallback.key, True
                except Exception as exc:
                    raise ProviderUnavailableError(
                        f"primary and fallback failed ({primary_error}; {fallback.key}: {exc})"
                    ) from exc

        raise ProviderUnavailableError(
            f"no callable provider for capability ({primary_error or 'primary not healthy'})"
        )

    # --- pipeline --------------------------------------------------------

    def call(
        self,
        ctx: ExecutionContext,
        capability_key: str,
        payload: dict[str, Any],
        output_model: type[BaseModel] | None = None,
    ) -> CapabilityCallResult:
        # 1-2. profile (permission/isolation)
        profile = self._resolve_profile(ctx)
        if ctx.profile_id is not None and profile is None:
            result = self._blocked(ctx, capability_key, "profile does not belong to workspace")
            return result

        # 3. capability
        cap = self.capability_registry.get_by_key(capability_key)
        if cap is None or cap.status != "ACTIVE":
            return self._blocked(ctx, capability_key, "unknown or inactive capability")

        if not self._profile_allowed(cap, profile):
            return self._blocked(ctx, capability_key, "profile not allowed for capability")

        # 4-5. provider + quota
        try:
            self._check_quota(cap, ctx)
            output, provider_key, fallback_used = self._execute(cap, payload)
        except QuotaExceeded as exc:
            return self._limited(ctx, capability_key, str(exc))
        except ProviderUnavailableError as exc:
            return self._unavailable(ctx, capability_key, str(exc))
        except Exception as exc:  # provider crash → same contract, audited
            return self._unavailable(ctx, capability_key, f"provider error: {exc}")

        # 6-7. validate output schema
        if output_model is not None:
            try:
                validated = output_model.model_validate(output)
                output = validated.model_dump(mode="json")
            except ValidationError as exc:
                audit_id = self._audit_call(
                    ctx, capability_key, provider_key, fallback_used,
                    CallStatus.VALIDATION_ERROR, reason=str(exc.errors()[:3]),
                )
                return CapabilityCallResult(
                    status=CallStatus.VALIDATION_ERROR,
                    provider_used=provider_key,
                    fallback_used=fallback_used,
                    audit_id=audit_id,
                    reason="output failed schema validation",
                )

        # 8. audit
        audit_id = self._audit_call(
            ctx, capability_key, provider_key, fallback_used, CallStatus.OK
        )
        return CapabilityCallResult(
            status=CallStatus.OK,
            output=output,
            provider_used=provider_key,
            fallback_used=fallback_used,
            audit_id=audit_id,
        )

    # --- outcomes (all audited) ------------------------------------------

    def _audit_call(
        self,
        ctx: ExecutionContext,
        capability_key: str,
        provider_key: str | None,
        fallback_used: bool,
        status: CallStatus,
        reason: str | None = None,
    ) -> UUID:
        event = append_audit(
            self.session,
            ctx=ctx,
            action="CAPABILITY_CALL",
            new_state=status.value,
            reason=reason,
            provider=provider_key,
            metadata={
                "capability": capability_key,
                "fallback_used": fallback_used,
            },
        )
        return event.id

    def _finish(
        self, status: CallStatus, ctx: ExecutionContext, capability_key: str,
        provider_key: str | None, reason: str,
    ) -> CapabilityCallResult:
        audit_id = self._audit_call(ctx, capability_key, provider_key, False, status, reason)
        return CapabilityCallResult(
            status=status, provider_used=provider_key, audit_id=audit_id, reason=reason
        )

    def _blocked(self, ctx, capability_key, reason):
        return self._finish(CallStatus.POLICY_BLOCKED, ctx, capability_key, None, reason)

    def _limited(self, ctx, capability_key, reason):
        return self._finish(CallStatus.QUOTA_LIMITED, ctx, capability_key, None, reason)

    def _unavailable(self, ctx, capability_key, reason):
        return self._finish(CallStatus.UNAVAILABLE, ctx, capability_key, None, reason)


class ProviderUnavailableError(Exception):
    pass
