import pytest

from packages.providers.laya_shadow import evaluate_decisions
from scripts.laya_shadow import _load_dataset


class FakeProvider:
    capability_key = "laya.classify"

    def call(self, _capability, payload):
        return {
            "mode": "ADVISORY",
            "confidence_policy": "UNVALIDATED_DO_NOT_GATE",
            "package_version": "0.3.22",
            "checkpoint_revisions": {"multilingual": "reviewed-sha"},
            "routing": {"model": "multilingual"},
            "answers": {
                "topic": {"choice": "history"},
                "reliable": {"noul": 0.8},
                "severity": {"score": 1.2, "probabilities": {"0": 0.2, "1": 0.8}},
            },
        }


def test_evaluator_reports_per_question_metrics_without_source_state():
    case = {
        "id": "case-1",
        "state": {"text": "secret source text is not part of the report"},
        "questions": {
            "topic": {
                "type": "choice",
                "instructions": "Choose topic",
                "criteria": {"history": "history", "other": "other"},
            },
            "reliable": {"type": "noul", "instructions": "Is this reliable?"},
            "severity": {
                "type": "score",
                "instructions": "Rate severity",
                "criteria": ["low", "high"],
            },
        },
        "expected": {"topic": "history", "reliable": True, "severity": 1},
    }

    result = evaluate_decisions([case], FakeProvider())

    assert result["cases"] == 1
    assert result["questions"] == 3
    assert result["routing_counts"] == {"multilingual": 1}
    assert result["package_versions"] == {"0.3.22": 1}
    assert result["checkpoint_revisions"] == {"multilingual": {"reviewed-sha": 1}}
    assert result["per_question"]["topic"]["accuracy"] == 1.0
    assert result["per_question"]["reliable"]["accuracy"] == 1.0
    assert result["per_question"]["severity"]["mean_absolute_error"] == 0.2
    assert "secret source text" not in repr(result)


def test_dataset_loader_hashes_and_parses_local_jsonl(tmp_path):
    dataset = tmp_path / "labels.jsonl"
    row = (
        '{"id":"case-1","state":"historical text","questions":{},'
        '"expected":{}}\n'
    )
    dataset.write_text(row, encoding="utf-8")

    cases, digest = _load_dataset(dataset)

    assert cases == [{"id": "case-1", "state": "historical text", "questions": {}, "expected": {}}]
    assert len(digest) == 64


def test_dataset_loader_rejects_invalid_json_without_echoing_row(tmp_path):
    dataset = tmp_path / "invalid.jsonl"
    dataset.write_text('{"state":"private text" invalid}\n', encoding="utf-8")

    with pytest.raises(ValueError) as error:
        _load_dataset(dataset)
    assert "line 1" in str(error.value)
    assert "private text" not in str(error.value)
