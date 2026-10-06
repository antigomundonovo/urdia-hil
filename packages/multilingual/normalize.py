"""Normalização e validação do contrato de idioma (Emenda 014).

Regras: erro EXPLÍCITO em entrada inválida; nunca fallback silencioso
para português/inglês; nunca alterar um idioma explicitamente definido
sem decisão (aqui não alteramos nada — só normalizamos representação).
"""

from packages.multilingual.catalog import _BY_ALIAS, locale_entry

_LOCALE_SEGMENT = {
    "pt": {"br", "pt"},
    "en": {"us", "gb"},
    "es": {"es", "mx", "419"},
    "fr": {"fr"},
    "de": {"de"},
    "it": {"it"},
    "ja": {"jp"},
    "ko": {"kr"},
    "zh": {"cn", "tw"},
    "hi": {"in"},
    "ar": {"eg"},
    "ru": {"ru"},
}


class LanguageError(ValueError):
    """Idioma/locale inválido ou par incompatível — erro explícito."""


def _fold(raw: str) -> str:
    return raw.strip().lower().replace("_", "-").replace(" ", "-")


def _resolve_language_name(raw: str) -> str:
    """Resolve um NOME de idioma (nunca tag composta) para o código.

    "pt", "english", "brazilian-portuguese" → "pt"/"en".
    "pt-br" aqui é ERRO: tag composta não é nome de idioma.
    """
    folded = _fold(raw)
    if "-" in folded:
        raise LanguageError(
            f"language_code deve ser o idioma canônico, não a tag composta: {raw!r}"
        )
    entry = _BY_ALIAS.get(folded)
    if entry is None:
        raise LanguageError(f"idioma não catalogado: {raw!r}")
    return entry.code


def normalize_language_tag(raw: str) -> tuple[str, str | None]:
    """Normaliza uma tag composta ("pt-BR", "pt_BR", "PT-br", "en-US").

    Devolve (language_code, locale_code|None). locale_code é None quando
    a tag só nomeia o idioma ("pt", "english").
    """
    folded = _fold(raw)
    whole = _BY_ALIAS.get(folded)
    if whole is not None:
        return whole.code, None
    parts = folded.split("-", 1)
    language_code = _resolve_language_name(parts[0])
    if len(parts) == 1:
        return language_code, None
    region = parts[1]
    if region in _BY_ALIAS:
        # palavra no lugar de região ("pt-português") não é localidade
        raise LanguageError(f"locale não catalogado para {language_code}: {raw!r}")
    if region not in _LOCALE_SEGMENT.get(language_code, set()):
        raise LanguageError(f"locale não catalogado para {language_code}: {raw!r}")
    locale_code = f"{language_code}-{region}"
    if locale_entry(locale_code) is None:
        raise LanguageError(f"locale não catalogado: {raw!r}")
    return language_code, locale_code


def normalize_language_pair(
    language_code: str | None, locale_code: str | None
) -> tuple[str, str | None]:
    """Normaliza o par já separado, validando compatibilidade.

    O locale aceita a região ("br", "BR") ou o locale canônico completo
    ("pt-br"). Locale sem idioma é erro (contrato exige language_code
    explícito).
    """
    if language_code is None or not language_code.strip():
        if locale_code and locale_code.strip():
            raise LanguageError("locale_code sem language_code: informe o idioma")
        raise LanguageError("language_code obrigatório")
    lang = _resolve_language_name(language_code)
    if locale_code is None or not locale_code.strip():
        return lang, None
    region = _fold(locale_code)
    if "-" in region:
        if not region.startswith(lang + "-"):
            raise LanguageError(f"locale incompatível com o idioma {lang}: {locale_code!r}")
        region = region.split("-", 1)[1]
    if region not in _LOCALE_SEGMENT.get(lang, set()):
        raise LanguageError(f"locale incompatível com o idioma {lang}: {locale_code!r}")
    canonical = f"{lang}-{region}"
    if locale_entry(canonical) is None:
        raise LanguageError(f"locale não catalogado: {locale_code!r}")
    return lang, canonical


def validate_pair(language_code: str, locale_code: str | None) -> None:
    """Valida par canônico JÁ PERSISTIDO; erro explícito se incoerente.

    Mais estrito que normalize_language_pair: aqui os valores têm de
    estar já em forma canônica (ex.: language_code="pt",
    locale_code="pt-br"; nunca "pt-BR" nem "pt_br").
    """
    lang_canonical = language_code.strip().lower()
    if language_code != lang_canonical or "-" in language_code or "_" in language_code:
        raise LanguageError(f"language_code deve ser canônico e simples: {language_code!r}")
    if locale_code:
        if locale_code != locale_code.strip().lower() or "_" in locale_code:
            raise LanguageError(f"locale_code deve ser canônico: {locale_code!r}")
        if not locale_code.startswith(language_code + "-"):
            raise LanguageError(
                f"locale incompatível com o idioma {language_code}: {locale_code!r}"
            )
    normalize_language_pair(language_code, locale_code)
