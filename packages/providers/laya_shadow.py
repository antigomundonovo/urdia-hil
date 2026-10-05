"""Offline evaluation of advisory Laya decisions against reviewed labels."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from packages.providers.laya import LayaDecisionProvider


def _score_label(answer: Mapping[str, Any]) -> int:
    probabilities = answer.get("probabilities")
    if isinstance(probabilities, Mapping) and probabilities:
        parsed: list[tuple[int, float]] = []
        for key, value in probabilities.items():
            try:
                index = int(key)
                probability = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("score answer has invalid probability entries") from exc
            if index < 0 or not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("score answer has invalid probability entries")
            parsed.append((index, probability))
        return max(parsed, key=lambda item: item[1])[0]

    score = answer.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError("score answer is missing a finite score")
    return round(score)


def _prediction(kind: str, answer: Mapping[str, Any]) -> Any:
    if kind == "choice":
        value = answer.get("choice")
        if not isinstance(value, str):
            raise ValueError("choice answer is missing its label")
        return value
    if kind == "noul":
        probability = answer.get("noul")
        if (
            isinstance(probability, bool)
            or not isinstance(probability, (int, float))
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
        ):
            raise ValueError("noul answer is missing a valid probability")
        return probability >= 0.5
    if kind == "score":
        return _score_label(answer)
    raise ValueError(f"unsupported question type: {kind}")


def evaluate_decisions(
    cases: Iterable[dict[str, Any]],
    provider: LayaDecisionProvider,
) -> dict[str, Any]:
    """Evaluate typed decisions without retaining source states or instructions.

    Each case has ``id``, ``state``, ``questions``, ``expected`` and optional
    ``lang``. Errors abort evaluation so an incomplete run cannot look like a
    successful report.
    """
    question_counts: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"kind": None, "total": 0, "correct": 0, "score_absolute_error": 0.0}
    )
    routing_counts: dict[str, int] = defaultdict(int)
    package_versions: dict[str, int] = defaultdict(int)
    checkpoint_revisions: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    processed = 0

    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"case {index} must be a JSON object")
        questions = case.get("questions")
        expected = case.get("expected")
        if not isinstance(questions, dict) or not isinstance(expected, dict):
            raise ValueError(f"case {index} needs questions and expected objects")
        if set(questions) != set(expected):
            raise ValueError(f"case {index} expected keys must match question keys")

        payload = {
            "state": case.get("state"),
            "questions": questions,
        }
        if "lang" in case:
            payload["lang"] = case["lang"]
        result = provider.call(LayaDecisionProvider.capability_key, payload)
        if result.get("mode") != "ADVISORY" or result.get(
            "confidence_policy"
        ) != "UNVALIDATED_DO_NOT_GATE":
            raise ValueError("provider response is missing advisory safeguards")
        package_version = result.get("package_version")
        if isinstance(package_version, str) and package_version:
            package_versions[package_version] += 1
        revisions = result.get("checkpoint_revisions")
        if isinstance(revisions, Mapping):
            for name, revision in revisions.items():
                if isinstance(name, str) and isinstance(revision, str) and revision:
                    checkpoint_revisions[name][revision] += 1

        answers = result.get("answers")
        if not isinstance(answers, dict) or set(answers) != set(questions):
            raise ValueError(f"case {index} provider answer keys do not match questions")
        routing = result.get("routing") or {}
        if isinstance(routing, dict):
            model = routing.get("model")
            if isinstance(model, str) and model:
                routing_counts[model] += 1

        for question_id, question in questions.items():
            kind = question.get("type")
            expected_value = expected[question_id]
            answer = answers[question_id]
            if not isinstance(answer, dict):
                raise ValueError(f"case {index} answer {question_id!r} must be an object")
            predicted = _prediction(kind, answer)
            if kind == "score":
                if (
                    isinstance(expected_value, bool)
                    or not isinstance(expected_value, int)
                ):
                    raise ValueError(
                        f"case {index} expected score {question_id!r} must be an integer label"
                    )
                # The score rubric's label indexes are positional and start at zero.
                if not 0 <= expected_value < len(question["criteria"]):
                    raise ValueError(
                        f"case {index} expected score {question_id!r} is outside its rubric"
                    )
                if not 0 <= predicted < len(question["criteria"]):
                    raise ValueError(
                        f"case {index} predicted score {question_id!r} is outside its rubric"
                    )
                raw_score = answer.get("score", predicted)
                if (
                    isinstance(raw_score, bool)
                    or not isinstance(raw_score, (int, float))
                    or not math.isfinite(raw_score)
                ):
                    raise ValueError(
                        f"case {index} score answer {question_id!r} has no finite score"
                    )
                value = float(raw_score)
                error = abs(value - expected_value)
            else:
                if kind == "noul" and not isinstance(expected_value, bool):
                    raise ValueError(
                        f"case {index} expected noul {question_id!r} must be boolean"
                    )
                if kind == "choice" and not isinstance(expected_value, str):
                    raise ValueError(
                        f"case {index} expected choice {question_id!r} must be a label"
                    )
                if kind == "choice":
                    criteria = question["criteria"]
                    valid_labels = criteria.keys() if isinstance(criteria, Mapping) else criteria
                    if expected_value not in valid_labels:
                        raise ValueError(
                            f"case {index} expected choice {question_id!r} is not in its options"
                        )
                error = 0.0

            metrics = question_counts[question_id]
            if metrics["kind"] not in (None, kind):
                raise ValueError(f"question {question_id!r} changes type between cases")
            metrics["kind"] = kind
            metrics["total"] += 1
            metrics["correct"] += int(predicted == expected_value)
            metrics["score_absolute_error"] += error

        processed += 1
    if not processed:
        raise ValueError("evaluation dataset is empty")

    summary: dict[str, Any] = {
        "cases": processed,
        "questions": sum(item["total"] for item in question_counts.values()),
        "routing_counts": dict(sorted(routing_counts.items())),
        "package_versions": dict(sorted(package_versions.items())),
        "checkpoint_revisions": {
            name: dict(sorted(revisions.items()))
            for name, revisions in sorted(checkpoint_revisions.items())
        },
        "per_question": {},
    }
    for question_id, metrics in sorted(question_counts.items()):
        entry = {
            "type": metrics["kind"],
            "total": metrics["total"],
            "correct": metrics["correct"],
            "accuracy": round(metrics["correct"] / metrics["total"], 6),
        }
        if metrics["kind"] == "score":
            entry["mean_absolute_error"] = round(
                metrics["score_absolute_error"] / metrics["total"], 6
            )
        summary["per_question"][question_id] = entry
    return summary
