"""Benchmark harness (Doc 16: initial set 100–300 cases) + Doc 07 backup
scripts runner entry."""

import sys

sys.path.insert(0, ".")

from packages.research.analyzers import check_anti_slop, check_originality  # noqa: E402
from packages.research.analytics import classify_comment  # noqa: E402
from packages.research.discovery import canonicalize_url  # noqa: E402
from packages.research.photos import detect_mime  # noqa: E402
from packages.research.photos import perceptual_hash  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []  # (suite, name, outcome)


def case(suite: str, name: str, actual, expected):
    outcome = PASS if actual == expected else FAIL
    results.append((suite, name, outcome))


# --- suite: rights gate (Doc 11/16) ---------------------------------------
from packages.domain.enums import RightsClassification, rights_gate  # noqa: E402
from packages.domain.enums import RightsGateOutcome  # noqa: E402

for classification in RightsClassification:
    gate = rights_gate(classification)
    if classification in (
        RightsClassification.UNKNOWN,
        RightsClassification.PROHIBITED,
        RightsClassification.PERMISSION_REQUIRED,
    ):
        case("rights", f"gate blocks {classification.value}", gate, RightsGateOutcome.BLOCK)
    else:
        case("rights", f"gate allows {classification.value}", gate, RightsGateOutcome.MAY_PROCEED)

# --- suite: knowledge states -------------------------------------------------
from packages.domain.enums import OpportunityState, UncertaintyState  # noqa: E402
from packages.domain.state_machine import can_transition  # noqa: E402

chain = [
    ("DISCOVERED", "NORMALIZED"), ("NORMALIZED", "CLUSTERED"), ("CLUSTERED", "CANDIDATE"),
    ("CANDIDATE", "RESEARCHING"), ("RESEARCHING", "EVIDENCE_COLLECTED"),
    ("EVIDENCE_COLLECTED", "FACT_CHECK"), ("FACT_CHECK", "UNCERTAINTY_REVIEW"),
    ("UNCERTAINTY_REVIEW", "OPPORTUNITY_SCORED"), ("OPPORTUNITY_SCORED", "FORMAT_SELECTED"),
    ("FORMAT_SELECTED", "PLATFORM_SELECTED"), ("PLATFORM_SELECTED", "DRAFTING"),
    ("DRAFTING", "VISUAL_PRODUCTION"), ("VISUAL_PRODUCTION", "RIGHTS_CHECK"),
    ("RIGHTS_CHECK", "SEO_CHECK"), ("SEO_CHECK", "QUALITY_CONTROL"),
    ("QUALITY_CONTROL", "HUMAN_REVIEW"), ("HUMAN_REVIEW", "READY"),
    ("READY", "SCHEDULED"), ("SCHEDULED", "PUBLISHED"), ("PUBLISHED", "ANALYZING"),
    ("ANALYZING", "LEARNING"),
]
for current, target in chain:
    case("state_machine", f"legal {current}→{target}",
         can_transition(OpportunityState(current), OpportunityState(target)), True)

illegal = [
    ("DISCOVERED", "PUBLISHED"), ("DISCOVERED", "READY"), ("RESEARCHING", "READY"),
    ("READY", "DRAFTING"), ("RESEARCHING", "CANDIDATE"), ("PUBLISHED", "REJECTED"),
    ("LEARNING", "DISCOVERED"), ("SCHEDULED", "REJECTED"), ("QUALITY_CONTROL", "PUBLISHED"),
    ("DRAFTING", "READY"),
]
for current, target in illegal:
    case("state_machine", f"illegal {current}→{target}",
         can_transition(OpportunityState(current), OpportunityState(target)), False)

# --- suite: comment classifier (Doc 15) ------------------------------------
comment_cases = [
    ("Qual a fonte desse dado?", "SOURCE_REQUEST"),
    ("Mostra a fonte, por favor", "SOURCE_REQUEST"),
    ("Onde viu isso?", "SOURCE_REQUEST"),
    ("Você errou, na verdade foi 1931", "CORRECTION"),
    ("Isso está errado, o certo é outro ano", "CORRECTION"),
    ("Tenho uma foto do meu avô na inauguração", "DOCUMENT_SUBMISSION"),
    ("Existe um documento sobre isso no arquivo", "DOCUMENT_SUBMISSION"),
    ("Minha avó trabalhava lá e contava histórias", "TESTIMONY"),
    ("Meu pai contava que era assim", "TESTIMONY"),
    ("E depois? Continua!", "CONTINUATION_REQUEST"),
    ("Faz uma parte 2!", "CONTINUATION_REQUEST"),
    ("Que foto incrível", None),
    ("Adorei a explicação", None),
    ("Ganhe seguidores clique aqui http://x.test", None),  # spam → signal None
    ("promoção imperdível https://spam.test visite", None),
    ("Isso é verdade?", "RECURRING_QUESTION"),
    ("Quem fotografou isso?", "RECURRING_QUESTION"),
]
for text, expected in comment_cases:
    _, signal = classify_comment(text)
    case("comments", f"signal {text[:32]!r}", signal, expected)

# --- suite: URL canonicalization / dedup (Doc 09) ----------------------------
url_cases = [
    ("https://Site.test/Pagina?utm_source=x#top", "https://site.test/Pagina"),
    ("http://site.test:80/a", "http://site.test/a"),
    ("https://site.test:443/a", "https://site.test/a"),
    ("https://site.test:80/a", "https://site.test:80/a"),
    ("http://site.test:443/a", "http://site.test:443/a"),
    ("https://[2001:db8::1]:443/a", "https://[2001:db8::1]/a"),
    ("https://site.test/x?b=2&a=1", "https://site.test/x?a=1&b=2"),
    ("https://site.test/x?fbclid=zz", "https://site.test/x"),
    ("HTTPS://SITE.TEST/Caminho", "https://site.test/Caminho"),
]
for raw, expected in url_cases:
    case("discovery", f"canonical {raw[:36]!r}", canonicalize_url(raw), expected)

# --- suite: upload security (Doc 08 magic bytes) -----------------------------
mime_cases = [
    (b"\xff\xd8\xffjunk", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\njunk", "image/png"),
    (b"RIFF1234WEBPVP8", "image/webp"),
    (b"II*\x00junk", "image/tiff"),
    (b"<html>nope</html>", None),
    (b"", None),
    (b"GIF89a", None),  # GIF not in allowlist
]
for content, expected in mime_cases:
    case("upload", f"mime {content[:12]!r}", detect_mime(content), expected)

# --- suite: perceptual hash (Doc 10) -----------------------------------------
def _png(pattern):
    import struct, zlib

    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + pattern(i) for i in range(8))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


vertical = _png(lambda i: bytes([i * 30] * 24))  # gradient down the rows
horizontal = _png(lambda i: bytes(range(3, 75, 3)))  # gradient across columns
case("photo", "phash deterministic", perceptual_hash(vertical), perceptual_hash(vertical))
case("photo", "phash discriminates", perceptual_hash(vertical) != perceptual_hash(horizontal), True)
case("photo", "phash never invents", perceptual_hash(b"nope"), None)

# --- suite: originality (Doc 16) ---------------------------------------------
source_text = "O bondinho foi inaugurado em 1912 e marcou o turismo carioca para sempre."
case("originality", "exact copy fails",
     check_originality(source_text, [("s1", source_text)]).result, "FAIL")
case("originality", "original passes",
     check_originality("A engenharia de 1912 enfrentava ventos fortes no morro.",
                       [("s1", source_text)]).result, "PASS")
case("originality", "nothing to compare warns",
     check_originality("texto qualquer", []).result, "WARNING")
near = source_text + " Veja só!"
case("originality", "near copy flagged",
     check_originality(near, [("s1", source_text)]).result in ("FAIL", "WARNING"), True)

# --- suite: anti-slop ----------------------------------------------------------
case("anti_slop", "cliché flagged",
     check_anti_slop("Desvende segredos", "Um mergulho na história.").result, "WARNING")
case("anti_slop", "clean passes",
     check_anti_slop("A padroeira", "O TSE vai julgar a decisão.").result, "PASS")

# --- suite: uncertainty vocabulary (Doc 00 §12) -------------------------------
expected_uncertainty = {"CONFIRMED", "PROBABLE", "POSSIBLE", "CONTROVERSIAL", "UNKNOWN", "REFUTED"}
case("vocabulary", "uncertainty complete",
     {s.value for s in UncertaintyState} == expected_uncertainty, True)

# --- suite: historical facts dataset (owner-provided, Doc 16) ------------------
# Owner-provided real historical facts are the canonical domain dataset
# (assets/datasets/historical_facts.json). Structural validation here —
# verdict-level cases live in tests/test_historical_facts.py (need a DB).
import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_DATASET = _Path("assets/datasets/historical_facts.json")
case("historical_dataset", "dataset exists", _DATASET.is_file(), True)
if _DATASET.is_file():
    _data = _json.loads(_DATASET.read_text(encoding="utf-8"))
    _cases = _data.get("cases", [])
    case("historical_dataset", "owner provided at least 3 cases", len(_cases) >= 3, True)
    case("historical_dataset", "case ids unique",
         len({c.get("id") for c in _cases}) == len(_cases), True)
    case("historical_dataset", "case statements unique",
         len({c.get("statement") for c in _cases}) == len(_cases), True)
    case("historical_dataset", "every case has https source",
         all(str(c.get("source_url", "")).startswith("https://") for c in _cases), True)
    case("historical_dataset", "every case has non-empty statement",
         all(str(c.get("statement", "")).strip() for c in _cases), True)
    _belief = [c for c in _cases if "popular_belief" in c]
    case("historical_dataset", "controversy case present (bondinho 1911 vs 1912)",
         len(_belief) >= 1, True)

# --- report --------------------------------------------------------------------
failed = [(s, n) for s, n, o in results if o == FAIL]
passed_count = len(results) - len(failed)
print(f"BENCHMARK (Doc 16): {len(results)} casos — {passed_count} PASS, {len(failed)} FAIL")
for suite, name in failed:
    print(f"  FAIL [{suite}] {name}")
sys.exit(1 if failed else 0)
