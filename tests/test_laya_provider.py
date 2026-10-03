import sys

import pytest

from packages.providers.laya import LayaDecisionProvider


class FakeRouter:
    def __init__(self):
        self.calls = []
        self.loaded_revisions = {"multilingual": "reviewed-sha"}

    def predict(self, state, questions, **kwargs):
        self.calls.append((state, questions, kwargs))
        return {
            "answers": {"topic": {"choice": "history", "answer_confidence": 0.8}},
            "routing": {"model": "english"},
        }


def _payload():
    return {
        "state": {"text": "A historical research note"},
        "questions": {
            "topic": {
                "type": "choice",
                "instructions": "Which topic fits `text`?",
                "criteria": {"history": "historical material", "other": "something else"},
            }
        },
    }


def test_laya_provider_returns_advisory_result_and_routes_language():
    router = FakeRouter()
    provider = LayaDecisionProvider(router=router)
    payload = _payload() | {"lang": "pt"}

    result = provider.call("laya.classify", payload)

    assert result["provider"] == "laya"
    assert result["mode"] == "ADVISORY"
    assert result["confidence_policy"] == "UNVALIDATED_DO_NOT_GATE"
    assert result["answers"]["topic"]["choice"] == "history"
    assert result["routing"]["model"] == "english"
    assert result["checkpoint_revisions"] == {"multilingual": "reviewed-sha"}
    assert router.calls == [
        (payload["state"], payload["questions"], {"lang": "pt"})
    ]


def test_laya_provider_initializes_router_lazily_and_only_once():
    router = FakeRouter()
    constructions = []

    def make_router():
        constructions.append(True)
        return router

    provider = LayaDecisionProvider(router_factory=make_router)
    provider.call("laya.classify", _payload())
    provider.call("laya.classify", _payload())

    assert len(constructions) == 1
    assert len(router.calls) == 2


@pytest.mark.parametrize(
    ("capability", "payload", "message"),
    [
        ("laya.other", _payload(), "unsupported Laya capability"),
        ("laya.classify", _payload() | {"model": "typed-decisions"}, "unsupported Laya payload"),
        (
            "laya.classify",
            _payload()
            | {
                "questions": {
                    "topic": {
                        "type": "choice",
                        "instructions": "Choose",
                        "criteria": {f"option-{i}": None for i in range(21)},
                    }
                }
            },
            "2 to 20 options",
        ),
        (
            "laya.classify",
            _payload()
            | {
                "questions": {
                    "topic": {
                        "type": "choice",
                        "instructions": "Choose",
                        "criteria": {"only": None},
                    }
                }
            },
            "2 to 20 options",
        ),
    ],
)
def test_laya_provider_rejects_unsupported_requests(capability, payload, message):
    provider = LayaDecisionProvider(router=FakeRouter())

    with pytest.raises(ValueError, match=message):
        provider.call(capability, payload)


def test_laya_provider_rejects_oversized_state_before_model_load():
    constructions = []
    provider = LayaDecisionProvider(router_factory=lambda: constructions.append(True))

    with pytest.raises(ValueError, match="exceeds 50000"):
        provider.call(
            "laya.classify",
            _payload() | {"state": "x" * 50_001},
        )

    assert constructions == []


def test_laya_provider_rejects_invalid_model_response():
    class InvalidRouter:
        def predict(self, *_args, **_kwargs):
            return {"routing": {}}

    provider = LayaDecisionProvider(router=InvalidRouter())

    with pytest.raises(RuntimeError, match="invalid decision response"):
        provider.call("laya.classify", _payload())


def test_missing_optional_laya_dependency_has_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "laya", None)

    with pytest.raises(RuntimeError, match="install URDIA with the 'laya' extra"):
        LayaDecisionProvider._default_router()
