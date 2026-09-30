"""Deterministic text analyzers (Doc 00 §21, Doc 16): originality + anti-slop.

ORIGINALITY (Doc 16 must-pass: exact copy, near-copy): word-shingle overlap
against source texts. Exact normalized copy → FAIL; heavy containment of one
source → WARNING "requires transformation"; otherwise PASS. Semantic-copy
detection needs embeddings (provider milestone) and remains out — the
deterministic layer never claims more than it computes.

ANTI-SLOP: pt-BR heuristic wordlists (cliché phrases, vague superlatives,
exclamation/caps/emoji spam). Never FAILs — slop is ultimately editorial
judgement; the gate flags and the human decides.
"""

import re
import unicodedata
from dataclasses import dataclass, field

_WORD_RE = re.compile(r"[\wáéíóúâêôãõçà]+", re.I)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "").lower()
    return " ".join(_WORD_RE.findall(text))


def shingles(text: str, n: int = 4) -> set[str]:
    words = normalize(text).split()
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def containment(a: set[str], b: set[str]) -> float:
    """How much of `a` lives inside `b` (0..1)."""
    if not a:
        return 0.0
    return len(a & b) / len(a)


@dataclass
class OriginalityResult:
    result: str  # PASS | WARNING | FAIL
    exact_copy_of: str | None = None
    near_copy_of: str | None = None
    containment: float = 0.0
    notes: list[str] = field(default_factory=list)


def check_originality(draft_text: str, sources: list[tuple[str, str]]) -> OriginalityResult:
    """sources: list of (reference, text). Exact/near copy detection via
    normalized shingles (Doc 16)."""
    draft = shingles(draft_text)
    if not draft or not sources:
        return OriginalityResult(result="WARNING", notes=["nothing to compare against"])

    normalized_draft = normalize(draft_text)
    for ref, text in sources:
        if normalize(text) == normalized_draft and normalized_draft:
            return OriginalityResult(
                result="FAIL", exact_copy_of=ref,
                notes=["exact copy of source — transformation required (Doc 16)"],
            )

    worst_ref, worst_score = None, 0.0
    for ref, text in sources:
        score = containment(draft, shingles(text))
        if score > worst_score:
            worst_ref, worst_score = ref, score

    if worst_score >= 0.7:
        return OriginalityResult(
            result="FAIL", near_copy_of=worst_ref, containment=worst_score,
            notes=[f"near-copy: {worst_score:.0%} of draft shingles from one source"],
        )
    if worst_score >= 0.4:
        return OriginalityResult(
            result="WARNING", near_copy_of=worst_ref, containment=worst_score,
            notes=[f"partial overlap {worst_score:.0%} with {worst_ref} — add original analysis"],
        )
    return OriginalityResult(result="PASS", containment=worst_score)


_SLOP_PHRASES = (
    "mergulhe em", "mergulhe na", "um mergulho na história", "desvende",
    "desvendando", "jornada épica", "tesouro escondido", "joia rara",
    "você não vai acreditar", "não vai acreditar no que", "chocante",
    "vai te surpreender", "poucos sabem", "segredos revelados",
    "prepare-se para se surpreender", "desde os tempos antigos",
    "como você nunca viu", "vai explodir sua mente",
)

_SUPERLATIVES = ("incrível", "impressionante", "surpreendente", "absurdo", "surreal")
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF]", flags=re.UNICODE
)


@dataclass
class AntiSlopResult:
    result: str  # PASS | WARNING (never FAIL — human judgement preserved)
    findings: list[str] = field(default_factory=list)


def check_anti_slop(title: str, caption: str) -> AntiSlopResult:
    findings: list[str] = []
    text = f"{title or ''}\n{caption or ''}"
    lowered = (text or "").lower()

    for phrase in _SLOP_PHRASES:
        if phrase in lowered:
            findings.append(f"clichê: “{phrase}”")

    superlative_count = sum(lowered.count(w) for w in _SUPERLATIVES)
    if superlative_count >= 3:
        findings.append(f"{superlative_count} superlativos vagos (incrível/impressionante/…)")

    if (text or "").count("!") > 2:
        findings.append("excesso de exclamações (>2)")

    words = _WORD_RE.findall(text or "")
    caps = [w for w in words if len(w) >= 4 and w.isupper()]
    if words and len(caps) / len(words) > 0.2:
        findings.append(f"{len(caps)} palavras em MAIÚSCULAS (>20%)")

    emoji_count = len(_EMOJI_RE.findall(text or ""))
    if emoji_count > 3:
        findings.append(f"{emoji_count} emojis (>3)")

    if findings:
        return AntiSlopResult(result="WARNING", findings=findings)
    return AntiSlopResult(result="PASS")
