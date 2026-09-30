"""Deterministic analyzers (Doc 16: exact copy, near-copy, anti-slop) +
real perceptual hash (Doc 10)."""

import struct
import zlib

from packages.research.analyzers import check_anti_slop, check_originality
from packages.research.photos import perceptual_hash

SOURCE = (
    "O bondinho do Pão de Açúcar foi inaugurado em 1912 e é um dos marcos "
    "do turismo carioca desde então, atraindo visitantes do mundo inteiro."
)


def test_exact_copy_fails():
    result = check_originality(SOURCE, [("fonte:1", SOURCE)])
    assert result.result == "FAIL"
    assert result.exact_copy_of == "fonte:1"


def test_near_copy_fails():
    near = SOURCE + " Confira!"
    result = check_originality(near, [("fonte:1", SOURCE)])
    assert result.result in ("FAIL", "WARNING")  # heavy overlap flagged
    assert result.containment > 0.6


def test_original_text_passes():
    original = (
        "Construir um Bondinho em pleno 1912 exigiu engenharia arrojada; "
        "o que dizem os registros oficiais sobre a concessão do serviço?"
    )
    result = check_originality(original, [("fonte:1", SOURCE)])
    assert result.result == "PASS"


def test_nothing_to_compare_warns_never_silent_pass():
    result = check_originality("qualquer texto", [])
    assert result.result == "WARNING"


def test_anti_slop_detects_cliche():
    result = check_anti_slop(
        "Desvende os segredos do passado",
        "Um mergulho na história que você não vai acreditar!",
    )
    assert result.result == "WARNING"
    assert any("clichê" in f for f in result.findings)


def test_anti_slop_clean_passes():
    result = check_anti_slop(
        "A padroeira em julgamento",
        "O TSE vai julgar a decisão que barrou postagens sobre Nossa Senhora Aparecida.",
    )
    assert result.result == "PASS"
    assert result.findings == []


def test_anti_slop_exclamation_and_caps():
    result = check_anti_slop(
        "ISSO É INCRÍVEL E ABSURDO E SURREAL",
        "INCRÍVEL!!! Não vai acreditar!!! EXISTE MAIS!!!",
    )
    assert result.result == "WARNING"


def _png(pattern) -> bytes:
    def chunk(typ, data):
        c = struct.pack(">I", len(data)) + typ + data
        return c + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + pattern(i) for i in range(8))
    end = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    return end + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_perceptual_hash_stable_and_discriminating():
    vertical = _png(lambda i: bytes([i * 30] * 24))  # gradient down the rows
    horizontal = _png(lambda i: bytes(range(3, 75, 3)))  # gradient across columns
    h1, h1_again = perceptual_hash(vertical), perceptual_hash(vertical)
    h2 = perceptual_hash(horizontal)
    assert h1 == h1_again  # deterministic
    assert h1 is not None and h1 != h2  # discriminates patterns
    assert perceptual_hash(b"not an image") is None  # never invents
