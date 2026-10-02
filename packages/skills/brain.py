"""URDIA BRAIN executor (AMENDMENT-2026-10-01-012).

A Recipe is a reviewed, code-declared chain of skills. The executor:
  1. validates every step's payload before running anything;
  2. runs skills in order, wiring declared inputs from previous results;
  3. stops at the recipe's terminal step — which for content recipes is
     ALWAYS a human gate (draft proposal / PENDING publication).

No LLM decides control flow in V1. New recipes = new reviewed code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.skills.base import SkillError
from packages.skills.catalog import build_skill_registry


@dataclass(frozen=True)
class Step:
    skill: str
    alias: str
    # maps this step's payload arg -> "<alias>.<result_key>" of a previous step
    input_from: dict[str, str] = field(default_factory=dict)
    optional: bool = False  # skipped (not fatal) if the skill is unavailable


@dataclass(frozen=True)
class Recipe:
    key: str
    description: str
    steps: tuple[Step, ...]
    # the recipe's declared human gate — documentation + runtime reminder
    human_gate: str


RECIPE_REGISTRY: dict[str, Recipe] = {
    "prepare_publication": Recipe(
        key="prepare_publication",
        description=(
            "Pacote aprovado -> proposta de rascunho (LLM, opcional) -> "
            "checagem do gate da plataforma -> export PENDING. Termina no "
            "Human Gate: confirm manual move PENDING -> PUBLISHED."
        ),
        steps=(
            Step(
                skill="scripting",
                alias="draft",
                input_from={"package_id": "$input.package_id"},
                optional=True,  # skipped when GOOGLE_AI_API_KEY is absent
            ),
            Step(
                skill="platform_policy",
                alias="gate",
                input_from={
                    "package_id": "$input.package_id",
                    "platform": "$input.platform",
                },
            ),
            Step(
                skill="publication",
                alias="export",
                input_from={
                    "package_id": "$input.package_id",
                    "platform": "$input.platform",
                },
            ),
        ),
        human_gate="POST /api/v1/publications/{id}/confirm (humano)",
    ),
    "factuality_audit": Recipe(
        key="factuality_audit",
        description=(
            "Auditoria factual do perfil: recomputa vereditos determinísticos "
            "de todas as claims (sem efeitos colaterais além dos próprios "
            "vereditos append-only)."
        ),
        steps=(Step(skill="factuality", alias="verdicts"),),
        human_gate="nenhum (somente leitura/recálculo auditado)",
    ),
    "factuality_challenge": Recipe(
        key="factuality_challenge",
        description=(
            "Comentário -> desafio factual (já criado via API) -> pesquisa nas "
            "fontes registradas -> judge determinístico -> veredito -> Human "
            "Gate de revisão. O comentário NUNCA é evidência por si (§11)."
        ),
        steps=(
            Step(skill="research", alias="sweep", input_from={
                "workspace_id": "$input.workspace_id",
                "profile_id": "$input.profile_id",
            }),
            Step(skill="factuality_challenge", alias="judged", input_from={
                "challenge_id": "$input.challenge_id",
            }),
        ),
        human_gate="POST /api/v1/social/challenges/{id}/review (humano)",
    ),
    "research_sweep": Recipe(
        key="research_sweep",
        description=(
            "Varre todas as fontes ativas do perfil (incl. YouTube) e "
            "coleta itens novos para o radar."
        ),
        steps=(Step(skill="research", alias="scan"),),
        human_gate="nenhum (coleta não publica nada)",
    ),
}


@dataclass
class StepResult:
    skill: str
    alias: str
    status: str  # OK | SKIPPED | FAILED
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BrainRun:
    """Result of a recipe run: per-step outcomes plus the human gate reminder."""

    def __init__(self, recipe: Recipe):
        self.recipe = recipe
        self.steps: list[StepResult] = []

    @property
    def ok(self) -> bool:
        return all(s.status in ("OK", "SKIPPED") for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe.key,
            "ok": self.ok,
            "steps": [
                {
                    "skill": s.skill,
                    "alias": s.alias,
                    "status": s.status,
                    "error": s.error,
                    "result": s.result,
                }
                for s in self.steps
            ],
            "human_gate": self.recipe.human_gate,
        }


def _resolve(value: Any, results: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, str) and value.startswith("$input."):
        return value  # resolved by the caller at run() time
    if isinstance(value, str) and "." in value and not value.startswith("$"):
        alias, key = value.split(".", 1)
        if alias in results and key in results[alias]:
            return results[alias][key]
    return value


def run_recipe(
    recipe_key: str,
    ctx,
    payload: dict[str, Any],
    registry=None,
) -> BrainRun:
    """Execute a recipe with the caller's ExecutionContext. The payload is
    the recipe input (e.g. package_id, platform)."""
    recipe = RECIPE_REGISTRY.get(recipe_key)
    if recipe is None:
        raise SkillError(f"unknown recipe: {recipe_key}")
    registry = registry or build_skill_registry()
    run = BrainRun(recipe)
    results: dict[str, dict[str, Any]] = {}

    for step in recipe.steps:
        try:
            skill = registry.get(step.skill)
        except SkillError as exc:
            run.steps.append(StepResult(step.skill, step.alias, "FAILED", error=str(exc)))
            return run
        base_payload = {
            arg: _resolve(source, results)
            for arg, source in step.input_from.items()
        }
        step_payload: dict[str, Any] = {}
        for arg, value in base_payload.items():
            if value == "$input." + arg:
                if arg in payload:
                    step_payload[arg] = payload[arg]
                    continue
                if step.optional:
                    continue
                raise SkillError(f"recipe {recipe_key}: input '{arg}' is required")
            step_payload[arg] = value
        # merge any extra direct inputs from the caller payload (opt-in keys)
        for arg in skill.required_payload_keys:
            step_payload.setdefault(arg, payload.get(arg))
        try:
            skill.validate_payload(step_payload)
            result = skill.invoke(ctx, step_payload)
            results[step.alias] = result
            run.steps.append(StepResult(step.skill, step.alias, "OK", result=result))
        except SkillError as exc:
            if step.optional and "GOOGLE_AI_API_KEY" in str(exc):
                run.steps.append(StepResult(step.skill, step.alias, "SKIPPED", error=str(exc)))
                continue
            run.steps.append(StepResult(step.skill, step.alias, "FAILED", error=str(exc)))
            return run
    return run


def list_recipes() -> list[dict[str, str]]:
    return [
        {
            "key": r.key,
            "description": r.description,
            "skills": " -> ".join(s.skill for s in r.steps),
            "human_gate": r.human_gate,
        }
        for r in RECIPE_REGISTRY.values()
    ]
