"""Provider-neutral platform adapter registry contract."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from packages.domain.enums import PlatformErrorKind, PublicationMethod
from packages.providers.platforms import (
    PlatformAdapterError,
    PlatformDescriptor,
    PlatformRegistry,
)


def _adapter(key: str):
    return SimpleNamespace(
        descriptor=PlatformDescriptor(
            key=key,
            capabilities=("publish_text",),
            publication_method=PublicationMethod.API,
            requirements={"account_type": "provider-defined"},
            limits={},
            quota={},
            analytics=("impressions",),
            status="UNAVAILABLE",
            last_verified=datetime.now(UTC),
        )
    )


def test_registry_requires_explicit_registration_and_returns_sorted_descriptors():
    registry = PlatformRegistry()
    registry.register(_adapter("zeta"))
    registry.register(_adapter("alpha"))

    assert [descriptor.key for descriptor in registry.descriptors()] == ["alpha", "zeta"]
    assert registry.get("alpha").descriptor.publication_method == PublicationMethod.API

    with pytest.raises(LookupError, match="not configured"):
        registry.get("unknown")


def test_registry_rejects_duplicate_and_invalid_keys():
    registry = PlatformRegistry()
    registry.register(_adapter("example"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(_adapter("example"))
    with pytest.raises(ValueError, match="lowercase identifier"):
        registry.register(_adapter("Not A Key"))


def test_platform_error_categories_match_documented_contract():
    assert {category.value for category in PlatformErrorKind} == {
        "AUTH_ERROR",
        "RATE_LIMIT",
        "POLICY_BLOCKED",
        "INVALID_PAYLOAD",
        "SERVER_ERROR",
        "NETWORK_ERROR",
        "UNAVAILABLE",
    }
    error = PlatformAdapterError(PlatformErrorKind.AUTH_ERROR)
    assert error.kind is PlatformErrorKind.AUTH_ERROR
    assert str(error) == "AUTH_ERROR"
