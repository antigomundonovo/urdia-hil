"""Run a local, side-effect-free Laya shadow evaluation over labelled JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from packages.providers.laya import LayaDecisionProvider
from packages.providers.laya_shadow import evaluate_decisions

MAX_DATASET_BYTES = 25 * 1024 * 1024
MAX_CASES = 5_000
MAX_LINE_BYTES = 1 * 1024 * 1024


def _load_dataset(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    if len(raw) > MAX_DATASET_BYTES:
        raise ValueError(f"dataset exceeds {MAX_DATASET_BYTES} bytes")
    digest = hashlib.sha256(raw).hexdigest()
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if len(line) > MAX_LINE_BYTES:
            raise ValueError(f"line {line_number} exceeds {MAX_LINE_BYTES} bytes")
        if not line.strip() or line.lstrip().startswith(b"#"):
            continue
        try:
            case = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON on line {line_number}") from exc
        if not isinstance(case, dict):
            raise ValueError(f"line {line_number} must contain a JSON object")
        cases.append(case)
        if len(cases) > MAX_CASES:
            raise ValueError(f"dataset exceeds {MAX_CASES} cases")
    if not cases:
        raise ValueError("dataset has no evaluation cases")
    return cases, digest


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare Laya's advisory decisions with reviewed labels. "
            "This command never changes editorial state or gates."
        )
    )
    parser.add_argument("dataset", type=Path, help="local labelled JSONL file")
    parser.add_argument("--report", type=Path, help="write a JSON summary report")
    args = parser.parse_args(argv)

    try:
        cases, dataset_hash = _load_dataset(args.dataset)
        result = evaluate_decisions(cases, LayaDecisionProvider())
        report = {
            "schema": "urdia-laya-shadow/1",
            "dataset_sha256": dataset_hash,
            "provider": "laya",
            "mode": "ADVISORY",
            "confidence_policy": "UNVALIDATED_DO_NOT_GATE",
            "decision_authority": "NONE",
            **result,
        }
        if args.report:
            _write_report(args.report, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(
            f"Laya shadow evaluation failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
