"""Optional Laya typed-decision provider.

This adapter is deliberately inert until a caller registers it for the
``laya.classify`` capability. Its output is advisory evidence only.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

MAX_STATE_CHARS = 50_000
MAX_QUESTIONS = 64
MAX_CHOICE_OPTIONS = 20
_ALLOWED_PAYLOAD_KEYS = {"state", "questions", "lang"}
_ALLOWED_QUESTION_KEYS = {"type", "instructions", "criteria", "labels"}


class LayaDecisionProvider:
    """Run local, typed Laya classifications through the provider contract."""

    key = "laya"
    capability_key = "laya.classify"

    def __init__(
        self,
        router: Any | None = None,
        router_factory: Callable[[], Any] | None = None,
    ) -> None:
        if router is not None and router_factory is not None:
            raise ValueError("provide router or router_factory, not both")
        self._router = router
        self._router_factory = router_factory or self._default_router
        self._lock = threading.Lock()

    @staticmethod
    def _default_router() -> Any:
        try:
            from laya import Router
        except ImportError as exc:
            raise RuntimeError(
                "Laya is optional; install URDIA with the 'laya' extra to use this provider"
            ) from exc

        return Router(preload=False, max_loaded=1, revision="reviewed")

    @staticmethod
    def _validate_payload(capability_key: str, payload: dict[str, Any]) -> None:
        if capability_key != LayaDecisionProvider.capability_key:
            raise ValueError(f"unsupported Laya capability: {capability_key}")
        if not isinstance(payload, dict):
            raise ValueError("Laya payload must be an object")
        unexpected = set(payload) - _ALLOWED_PAYLOAD_KEYS
        if unexpected:
            raise ValueError(f"unsupported Laya payload fields: {', '.join(sorted(unexpected))}")

        state = payload.get("state")
        if not isinstance(state, (str, dict, list)) or not state:
            raise ValueError("Laya state must be a non-empty string, object, or array")
        try:
            state_text = state if isinstance(state, str) else json.dumps(
                state, ensure_ascii=False, allow_nan=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Laya state must contain JSON-compatible data") from exc
        if len(state_text) > MAX_STATE_CHARS:
            raise ValueError(f"Laya state exceeds {MAX_STATE_CHARS} characters")

        questions = payload.get("questions")
        if not isinstance(questions, dict) or not questions:
            raise ValueError("Laya questions must be a non-empty object")
        if len(questions) > MAX_QUESTIONS:
            raise ValueError(f"Laya accepts at most {MAX_QUESTIONS} questions per call")

        for name, question in questions.items():
            if not isinstance(name, str) or not name:
                raise ValueError("Laya question names must be non-empty strings")
            if not isinstance(question, dict):
                raise ValueError(f"Laya question {name!r} must be an object")
            unknown = set(question) - _ALLOWED_QUESTION_KEYS
            if unknown:
                raise ValueError(
                    f"unsupported fields for Laya question {name!r}: "
                    f"{', '.join(sorted(unknown))}"
                )
            kind = question.get("type")
            if kind not in {"choice", "score", "noul"}:
                raise ValueError(f"Laya question {name!r} has an unsupported type")
            instructions = question.get("instructions")
            if not isinstance(instructions, str) or not instructions.strip():
                raise ValueError(f"Laya question {name!r} needs non-empty instructions")

            criteria = question.get("criteria")
            if kind == "choice":
                if isinstance(criteria, Mapping):
                    option_count = len(criteria)
                    if any(not isinstance(label, str) or not label for label in criteria):
                        raise ValueError(f"Laya choice {name!r} labels must be non-empty strings")
                elif isinstance(criteria, list):
                    option_count = len(criteria)
                    if any(not isinstance(label, str) or not label for label in criteria):
                        raise ValueError(f"Laya choice {name!r} labels must be non-empty strings")
                else:
                    raise ValueError(f"Laya choice {name!r} needs a criteria mapping or list")
                if not 2 <= option_count <= MAX_CHOICE_OPTIONS:
                    raise ValueError(
                        f"Laya choice {name!r} must have 2 to {MAX_CHOICE_OPTIONS} options"
                    )
            elif kind == "score":
                if not isinstance(criteria, list) or not 2 <= len(criteria) <= 32:
                    raise ValueError(f"Laya score {name!r} needs 2 to 32 ordered criteria")
                if any(not isinstance(label, str) or not label for label in criteria):
                    raise ValueError(f"Laya score {name!r} criteria must be non-empty strings")

            labels = question.get("labels")
            if labels is not None and (
                kind != "noul"
                or not isinstance(labels, dict)
                or set(labels) != {"false", "true"}
                or any(not isinstance(label, str) or not label for label in labels.values())
            ):
                raise ValueError(f"Laya labels for {name!r} must define non-empty false/true text")

        language = payload.get("lang")
        if language is not None and (
            not isinstance(language, str) or not language.strip() or len(language) > 32
        ):
            raise ValueError("Laya lang must be a non-empty language code of at most 32 characters")

    def _get_router(self) -> Any:
        if self._router is None:
            with self._lock:
                if self._router is None:
                    self._router = self._router_factory()
        return self._router

    def call(self, capability_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate_payload(capability_key, payload)
        kwargs = {}
        if "lang" in payload:
            kwargs["lang"] = payload["lang"]

        result = self._get_router().predict(
            payload["state"],
            payload["questions"],
            **kwargs,
        )
        if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
            raise RuntimeError("Laya returned an invalid decision response")

        routing = result.get("routing")
        if routing is not None and not isinstance(routing, dict):
            raise RuntimeError("Laya returned invalid routing metadata")
        try:
            package_version = version("laya")
        except PackageNotFoundError:
            package_version = "0.3.22"

        return {
            "provider": self.key,
            "package_version": package_version,
            "mode": "ADVISORY",
            "confidence_policy": "UNVALIDATED_DO_NOT_GATE",
            "answers": result["answers"],
            "routing": routing,
        }
