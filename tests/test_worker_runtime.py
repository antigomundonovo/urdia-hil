"""Worker process lifecycle tests that do not require PostgreSQL."""

from types import SimpleNamespace

from apps.worker import __main__ as worker


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self):
        pass


def test_running_jobs_are_recovered_once_at_worker_startup(monkeypatch):
    recovery_calls = 0
    claim_calls = 0

    class FakeEngine:
        def __init__(self, session, handlers):
            pass

        def recover_running(self):
            nonlocal recovery_calls
            recovery_calls += 1
            return 0

        def claim_next(self):
            nonlocal claim_calls
            claim_calls += 1
            if claim_calls == 1:
                return SimpleNamespace(id="job-1", job_type="DISCOVERY_SCAN", attempt=1)
            return None

        def run_job(self, job):
            job.status = "SUCCEEDED"

    def stop_worker(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "SessionLocal", _Session)
    monkeypatch.setattr(worker, "build_handlers", dict)
    monkeypatch.setattr("apps.worker.engine.JobEngine", FakeEngine)
    monkeypatch.setattr(worker.time, "sleep", stop_worker)

    assert worker.run_forever(poll_seconds=0) == 0
    assert recovery_calls == 1
    assert claim_calls == 2
