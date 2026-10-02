"""Adversarial research agent (Doc 16; contract §11 Judge path).

The LLM ONLY proposes search queries designed to REFUTE a claim. The
system then searches the registered external engines (GDELT news search,
Wikipedia) through the SafeFetcher (SSRF-guarded, rate-limited) and
returns CANDIDATES for human review. Candidates are NEVER evidence by
themselves: evidence enters only via the normal add_evidence path with
provenance, and the verdict stays with the deterministic judge (Doc 16).
Prompt is not governance (Doc 17 §10).
"""

from __future__ import annotations

import json
from urllib.parse import quote_plus

from packages.providers.gemini import ProviderError, ProviderUnavailable

ADVERSARIAL_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "queries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "engine": {"type": "string", "enum": ["gdelt", "wikipedia"]},
                    "rationale": {"type": "string"},
                },
                "required": ["query", "engine"],
            },
        }
    },
    "required": ["queries"],
}

PROMPT = (
    "Você é o pesquisador adversário da URDIA (antigo Mundo Novo: história do "
    "Rio de Janeiro). Dada a alegação factual abaixo, produza de 3 a 5 queries "
    "de busca em português e/ou inglês projetadas para ENCONTRAR EVIDÊNCIAS QUE "
    "CONTRADIGAM ou refutem a alegação (datas diferentes, versões concorrentes, "
    "contestações de fontes primárias). Use `engine: \"gdelt\"` para notícias/"
    "jornais e `engine: \"wikipedia\"` para verbetes. Nunca inclua a alegação "
    "integral na query: extraia os termos verificáveis (nomes, datas, lugares). "
    "Responda apenas no JSON do schema."
)

MAX_CANDIDATES_PER_ENGINE = 8


class AdversarialBlocked(Exception):
    """Fail closed: unusable model output."""


def generate_queries(provider, *, statement: str) -> list[dict]:
    try:
        result = provider.call(
            "llm.generate",
            {
                "prompt": f"{PROMPT}\n\nALEGAÇÃO:\n{statement}",
                "json_schema": ADVERSARIAL_JSON_SCHEMA,
                "temperature": 0.3,
            },
        )
    except ProviderUnavailable:
        raise
    except ProviderError as exc:
        raise AdversarialBlocked(f"provider content unusable: {exc}") from exc

    queries = (result.get("json") or {}).get("queries")
    if not isinstance(queries, list) or not queries:
        raise AdversarialBlocked("model returned no adversarial queries")
    cleaned = []
    for q in queries[:5]:
        text = str((q or {}).get("query", "")).strip()
        engine = str((q or {}).get("engine", "gdelt")).lower()
        if text and engine in ("gdelt", "wikipedia"):
            cleaned.append(
                {
                    "query": text,
                    "engine": engine,
                    "rationale": str((q or {}).get("rationale", "")).strip(),
                }
            )
    if not cleaned:
        raise AdversarialBlocked("all adversarial queries were invalid")
    return cleaned


def _gdelt_url(query: str) -> str:
    return (
        "https://api.gdeltproject.org/api/v2/doc/doc"
        f"?query={quote_plus(query)}&mode=artlist&maxrecords=10&format=json"
    )


def _wikipedia_url(query: str) -> str:
    return (
        "https://pt.wikipedia.org/w/api.php?action=query&format=json"
        f"&list=search&srlimit=5&srsearch={quote_plus(query)}"
    )


def _search_engine(engine: str, query: str, fetcher) -> list[dict]:
    url = _gdelt_url(query) if engine == "gdelt" else _wikipedia_url(query)
    try:
        result = fetcher.fetch(url)
    except Exception:
        return []  # engine failure never blocks the audit; candidates only
    if result.status_code != 200 or not result.content:
        return []
    try:
        payload = json.loads(result.content.decode("utf-8", errors="replace"))
    except ValueError:
        return []

    candidates: list[dict] = []
    if engine == "gdelt":
        for article in (payload.get("articles") or [])[:MAX_CANDIDATES_PER_ENGINE]:
            if not isinstance(article, dict):
                continue
            article_url = article.get("url")
            if not isinstance(article_url, str) or not article_url.startswith("http"):
                continue
            candidates.append(
                {
                    "engine": engine,
                    "url": article_url,
                    "title": article.get("title"),
                    "snippet": None,
                    "source_domain": article.get("domain"),
                    "query": query,
                }
            )
    else:
        for hit in ((payload.get("query") or {}).get("search") or [])[:5]:
            if not isinstance(hit, dict):
                continue
            candidates.append(
                {
                    "engine": engine,
                    "url": (
                        "https://pt.wikipedia.org/wiki/"
                        + quote_plus(str(hit.get("title", "")).replace(" ", "_"))
                    ),
                    "title": hit.get("title"),
                    "snippet": hit.get("snippet"),
                    "source_domain": "pt.wikipedia.org",
                    "query": query,
                }
            )
    return candidates


def run_adversarial(provider, fetcher, *, statement: str) -> dict:
    """Generate refutation queries and collect candidate sources. Pure
    read-only research: nothing is persisted, nothing is decided."""
    queries = generate_queries(provider, statement=statement)
    candidates: list[dict] = []
    for q in queries:
        candidates.extend(_search_engine(q["engine"], q["query"], fetcher))
    return {
        "queries": queries,
        "candidates": candidates,
        "note": (
            "candidates are LEADS for human review — they become evidence "
            "only through the normal add_evidence path with provenance (Doc 09)"
        ),
    }
