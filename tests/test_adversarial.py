"""Adversarial research tests — LLM queries and engine responses are mocked."""

import uuid
from types import SimpleNamespace

import pytest

from agents import adversarial as adv
from apps.worker import handlers_real
from apps.worker.engine import JOB_FAILED, JobEngine
from packages.providers.gemini import ProviderError, ProviderUnavailable


class DummySession:
    def flush(self):
        pass

    def commit(self):
        pass

    def add(self, obj):
        pass

    def get(self, model, key):
        return None


class FakeProvider:
    key = "fake"

    def __init__(self, result=None, error=None):
        self.result = result or {}
        self.error = error

    def call(self, capability_key, payload):
        if self.error:
            raise self.error
        return self.result


class FakeFetcher:
    def __init__(self, bodies: dict[str, bytes]):
        self.bodies = bodies
        self.fetched = []

    def fetch(self, url):
        self.fetched.append(url)
        for key, body in self.bodies.items():
            if key in url:
                return SimpleNamespace(status_code=200, content=body, url=url)
        return SimpleNamespace(status_code=200, content=b"{}", url=url)


def _llm_queries():
    return {
        "text": "json",
        "json": {
            "queries": [
                {"query": "bondinho 1912 inauguração", "engine": "gdelt"},
                {"query": "Bondinho Pão de Açúcar história", "engine": "wikipedia"},
            ]
        },
        "provider": "fake",
        "model": "fake-model",
    }


GDELT_BODY = (
    '{"articles": [{"url": "https://jornal.test/bondinho-1912", '
    '"title": "Bondinho teria começado em 1912", "domain": "jornal.test", '
    '"seendate": "20261001T120000Z"}]}'
).encode()
WIKI_BODY = (
    '{"query": {"search": [{"title": "Bondinho do Pão de Açúcar", '
    '"snippet": "inaugurado em <span>1911</span>"}]}}'
).encode()


def test_generate_queries_validates_shape():
    provider = FakeProvider(result=_llm_queries())
    queries = adv.generate_queries(provider, statement="O bondinho começou em 1911")
    assert len(queries) == 2
    assert queries[0]["engine"] == "gdelt"
    assert "bondinho" in queries[0]["query"].lower()


def test_generate_queries_rejects_empty():
    provider = FakeProvider(result={"text": "x", "json": {"queries": []}})
    with pytest.raises(adv.AdversarialBlocked, match="no adversarial queries"):
        adv.generate_queries(provider, statement="qualquer")


def test_generate_queries_provider_error_is_blocked():
    provider = FakeProvider(error=ProviderError("bad json"))
    with pytest.raises(adv.AdversarialBlocked):
        adv.generate_queries(provider, statement="x")


def test_run_adversarial_collects_candidates():
    provider = FakeProvider(result=_llm_queries())
    fetcher = FakeFetcher({"gdeltproject": GDELT_BODY, "wikipedia.org": WIKI_BODY})
    report = adv.run_adversarial(
        provider, fetcher, statement="O bondinho começou em 1911"
    )
    engines = {c["engine"] for c in report["candidates"]}
    assert engines == {"gdelt", "wikipedia"}
    gdelt = [c for c in report["candidates"] if c["engine"] == "gdelt"][0]
    assert gdelt["url"].startswith("https://jornal.test/")
    assert "add_evidence" in report["note"]


def test_engine_failure_never_blocks_the_audit():
    provider = FakeProvider(result=_llm_queries())

    class FailingFetcher:
        def fetch(self, url):
            raise RuntimeError("network down")

    report = adv.run_adversarial(provider, FailingFetcher(), statement="x")
    assert report["candidates"] == []
    assert len(report["queries"]) == 2


def test_handler_fails_closed_without_ids():
    handlers = {"ADVERSARIAL_RESEARCH": handlers_real.ADVERSARIAL_RESEARCH}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        job_type="ADVERSARIAL_RESEARCH",
        payload={},
        checkpoint={"completed_steps": [], "next_step": None},
        status="RUNNING",
        attempt=1,
        max_attempts=1,
        result=None,
        finished_at=None,
        error=None,
    )
    result = JobEngine(DummySession(), handlers).run_job(job)
    assert result.status == JOB_FAILED


def test_handler_provider_unavailable_requeues(db, monkeypatch):
    """Real claim in the real DB (handlers open their own connections)."""
    from packages.domain.enums import UncertaintyState
    from packages.domain.knowledge import Claim
    from packages.domain.models import Profile, Workspace

    ws = Workspace(name=f"adv-{uuid.uuid4().hex[:8]}")
    db.add(ws)
    db.flush()
    profile = Profile(workspace_id=ws.id, key="main", name="Main")
    db.add(profile)
    db.flush()
    claim = Claim(
        workspace_id=ws.id,
        profile_id=profile.id,
        normalized_text="O bondinho começou a operar em 1911",
        status=UncertaintyState.UNKNOWN.value,
    )
    db.add(claim)
    db.commit()

    handlers = {"ADVERSARIAL_RESEARCH": handlers_real.ADVERSARIAL_RESEARCH}
    job = SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        profile_id=profile.id,
        job_type="ADVERSARIAL_RESEARCH",
        payload={"claim_id": str(claim.id)},
        checkpoint={"completed_steps": [], "next_step": None},
        status="RUNNING",
        attempt=1,
        max_attempts=2,
        result=None,
        finished_at=None,
        error=None,
    )
    provider = FakeProvider(error=ProviderUnavailable("rate limited"))
    monkeypatch.setattr(handlers_real, "_adversarial_provider", lambda: provider)
    result = JobEngine(DummySession(), handlers).run_job(job)
    assert result.status == "PENDING"  # requeued (Doc 03 retryable)
    assert "provider unavailable" in (result.error or "")
