"""Governance tests (Doc 16 must-pass rules): profile isolation, quota,
provider fallback, fail-closed outcomes, schema validation, audit trail."""

import uuid

import pytest

from packages.domain.enums import HealthState
from packages.domain.models import Profile, Workspace
from packages.domain.repositories import AuditRepository
from packages.governance.capability_call import CallStatus, CapabilityCaller
from packages.governance.registries import CapabilityRegistry, ProviderRegistry
from packages.providers.base import EchoProvider, FailingProvider
from packages.shared.execution_context import ExecutionContext


@pytest.fixture()
def world(db):
    ws_a = Workspace(name=f"gov-a-{uuid.uuid4().hex[:8]}")
    db.add(ws_a)
    db.flush()
    profile_a = Profile(workspace_id=ws_a.id, key="a", name="A")
    db.add(profile_a)
    db.flush()
    return ws_a, profile_a


def _ctx(ws, profile) -> ExecutionContext:
    return ExecutionContext(workspace_id=ws.id, profile_id=profile.id)


def _caller(db, adapters=None):
    return CapabilityCaller(db, adapters or {"echo": EchoProvider(), "failing": FailingProvider()})


def test_unknown_capability_blocks(db, world):
    ws, profile = world
    result = _caller(db).call(_ctx(ws, profile), "no.such.capability", {})
    assert result.status is CallStatus.POLICY_BLOCKED
    assert result.output is None


def test_profile_from_foreign_workspace_blocked(db, world):
    ws_a, _ = world
    ws_b = Workspace(name=f"gov-b-{uuid.uuid4().hex[:8]}")
    db.add(ws_b)
    db.flush()
    profile_b = Profile(workspace_id=ws_b.id, key="b", name="B")
    db.add(profile_b)
    db.flush()

    ProviderRegistry(db).register("echo", health=HealthState.HEALTHY.value)
    cap = CapabilityRegistry(db).register("cap.iso", provider_id=None)

    # capability has no provider wired — but the isolation check fires first:
    # profile B does not belong to ws_a, so the call is blocked before anything else
    ctx = ExecutionContext(workspace_id=ws_a.id, profile_id=profile_b.id)
    result = _caller(db).call(ctx, "cap.iso", {})
    assert result.status is CallStatus.POLICY_BLOCKED
    assert "does not belong" in result.reason
    db.rollback()  # discard cap/provider registrations

    # mark fixtures unused for linters
    assert cap.key == "cap.iso"


def test_allowed_profiles_empty_means_all(db, world):
    ws, profile = world
    echo = EchoProvider()
    pr = ProviderRegistry(db).register("echo", health=HealthState.HEALTHY.value)
    CapabilityRegistry(db).register("cap.open", provider_id=pr.id, allowed_profiles=None)
    result = _caller(db, {"echo": echo}).call(_ctx(ws, profile), "cap.open", {"k": 1})
    assert result.status is CallStatus.OK
    assert result.output["echoed"] == {"k": 1}


def test_allowed_profiles_restriction_blocks_other_profiles(db, world):
    ws, profile = world
    pr = ProviderRegistry(db).register("echo", health=HealthState.HEALTHY.value)
    CapabilityRegistry(db).register("cap.restricted", provider_id=pr.id, allowed_profiles=["vip"])
    result = _caller(db).call(_ctx(ws, profile), "cap.restricted", {})
    assert result.status is CallStatus.POLICY_BLOCKED
    assert "not allowed" in result.reason


def test_quota_exceeded_fails_closed(db, world):
    ws, profile = world
    echo = EchoProvider()
    pr = ProviderRegistry(db).register("echo", health=HealthState.HEALTHY.value)
    CapabilityRegistry(db).register(
        "cap.quota", provider_id=pr.id, quota={"max_calls_per_day": 1}
    )
    caller = _caller(db, {"echo": echo})
    first = caller.call(_ctx(ws, profile), "cap.quota", {})
    assert first.status is CallStatus.OK
    second = caller.call(_ctx(ws, profile), "cap.quota", {})
    assert second.status is CallStatus.QUOTA_LIMITED


def test_primary_failure_falls_back_with_same_contract(db, world):
    ws, profile = world
    echo = EchoProvider()
    failing = FailingProvider()
    primary = ProviderRegistry(db).register("failing", health=HealthState.HEALTHY.value)
    backup = ProviderRegistry(db).register("echo", health=HealthState.HEALTHY.value)
    CapabilityRegistry(db).register(
        "cap.fallback", provider_id=primary.id, fallback_provider_id=backup.id
    )
    result = _caller(db, {"echo": echo, "failing": failing}).call(
        _ctx(ws, profile), "cap.fallback", {"x": 2}
    )
    assert result.status is CallStatus.OK
    assert result.fallback_used is True
    assert result.provider_used == "echo"
    assert failing.attempts  # primary was actually tried first


def test_all_providers_down_is_unavailable(db, world):
    ws, profile = world
    primary = ProviderRegistry(db).register("p1", health=HealthState.UNAVAILABLE.value)
    backup = ProviderRegistry(db).register("p2", health=HealthState.QUOTA_LIMITED.value)
    CapabilityRegistry(db).register(
        "cap.down", provider_id=primary.id, fallback_provider_id=backup.id
    )
    result = _caller(db).call(_ctx(ws, profile), "cap.down", {})
    assert result.status is CallStatus.UNAVAILABLE


def test_invalid_output_fails_validation_and_audits(db, world):
    from pydantic import BaseModel

    class Strict(BaseModel):
        required_field: str

    ws, profile = world
    echo = EchoProvider()
    pr = ProviderRegistry(db).register("echo", health=HealthState.HEALTHY.value)
    CapabilityRegistry(db).register("cap.strict", provider_id=pr.id)
    result = _caller(db, {"echo": echo}).call(
        _ctx(ws, profile), "cap.strict", {"nope": 1}, output_model=Strict
    )
    assert result.status is CallStatus.VALIDATION_ERROR
    events = AuditRepository(db).list_for_workspace(ws.id, limit=5)
    assert any(e.new_state == CallStatus.VALIDATION_ERROR.value for e in events)


def test_every_call_is_audited_with_provider_and_capability(db, world):
    ws, profile = world
    echo = EchoProvider()
    pr = ProviderRegistry(db).register("echo", health=HealthState.HEALTHY.value)
    CapabilityRegistry(db).register("cap.audit", provider_id=pr.id)
    result = _caller(db, {"echo": echo}).call(_ctx(ws, profile), "cap.audit", {})
    assert result.status is CallStatus.OK
    events = [
        e
        for e in AuditRepository(db).list_for_workspace(ws.id, limit=10)
        if e.action == "CAPABILITY_CALL"
    ]
    assert len(events) == 1
    assert events[0].metadata_["capability"] == "cap.audit"
    assert events[0].metadata_["fallback_used"] is False
    assert events[0].provider == "echo"


def test_audit_repository_is_append_only_surface(db, world):
    ws, _ = world
    repo = AuditRepository(db)
    assert not hasattr(repo, "delete")
    assert not hasattr(repo, "update")
    assert not hasattr(repo, "remove")
