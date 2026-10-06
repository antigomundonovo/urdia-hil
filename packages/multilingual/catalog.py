"""Catálogo central de idiomas — fonte única de verdade (Emenda 014).

Capacidades (tts/captions) são configuração editorial explícita: só
marque `tts=True` quando existir rota técnica real no HIL. Não invente
capacidade. `default_locale` é a localidade padrão editorial, não uma
dedução automática.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Locale:
    code: str  # canonical locale_code, ex. "pt-br"
    name: str  # leigo, ex. "Português do Brasil"


@dataclass(frozen=True)
class Language:
    code: str  # canonical language_code, ex. "pt"
    name: str  # leigo, ex. "Português"
    aliases: tuple[str, ...] = field(default=())
    locales: tuple[Locale, ...] = field(default=())
    tts_support: bool = False
    captions_support: bool = True

    @property
    def default_locale(self) -> Locale | None:
        """Localidade padrão editorial (primeira do catálogo)."""
        return self.locales[0] if self.locales else None


def _l(
    code: str,
    name: str,
    aliases: tuple[str, ...],
    locales: tuple[tuple[str, str], ...],
    *,
    tts: bool = False,
) -> Language:
    # aliases já em forma normalizada (minúsculas, "-" como separador)
    return Language(
        code=code,
        name=name,
        aliases=tuple(a.strip().lower().replace("_", "-").replace(" ", "-") for a in aliases),
        locales=tuple(Locale(c, n) for c, n in locales),
        tts_support=tts,
        captions_support=True,
    )


# tts=True apenas onde existe rota técnica real hoje (nenhuma integrada
# no HIL V1) — mantido False por padrão; ajustar por decisão editorial
# com implementação, nunca por otimismo.
LANGUAGES: tuple[Language, ...] = (
    _l(
        "pt",
        "Português",
        (
            "portuguese",
            "portugues",
            "brazilian-portuguese",
            "português-brasileiro",
            "portugues-brasileiro",
        ),
        (("pt-br", "Português do Brasil"), ("pt-pt", "Português de Portugal")),
    ),
    _l(
        "en",
        "Inglês",
        ("english", "ingles", "inglés"),
        (("en-us", "Inglês (EUA)"), ("en-gb", "Inglês (Reino Unido)")),
    ),
    _l(
        "es",
        "Espanhol",
        ("spanish", "espanhol", "español"),
        (
            ("es-es", "Espanhol (Espanha)"),
            ("es-mx", "Espanhol (México)"),
            ("es-419", "Espanhol (América Latina)"),
        ),
    ),
    _l("fr", "Francês", ("french", "francês", "français"), (("fr-fr", "Francês (França)"),)),
    _l("de", "Alemão", ("german", "alemão", "deutsch"), (("de-de", "Alemão (Alemanha)"),)),
    _l("it", "Italiano", ("italian", "italiano"), (("it-it", "Italiano (Itália)"),)),
    _l("ja", "Japonês", ("japanese", "japonês"), (("ja-jp", "Japonês (Japão)"),)),
    _l("ko", "Coreano", ("korean", "coreano"), (("ko-kr", "Coreano (Coreia do Sul)"),)),
    _l(
        "zh",
        "Chinês",
        ("chinese", "chinês", "mandarin", "mandarim"),
        (("zh-cn", "Chinês simplificado"), ("zh-tw", "Chinês tradicional")),
    ),
    _l("hi", "Hindi", ("hindi",), (("hi-in", "Hindi (Índia)"),)),
    _l("ar", "Árabe", ("arabic", "árabe"), (("ar-eg", "Árabe (Egito)"),)),
    _l("ru", "Russo", ("russian", "russo"), (("ru-ru", "Russo (Rússia)"),)),
)

_BY_LANGUAGE = {lang.code: lang for lang in LANGUAGES}
_BY_ALIAS = {}
for _lang in LANGUAGES:
    _BY_ALIAS[_lang.code] = _lang
    for _alias in _lang.aliases:
        _BY_ALIAS[_alias] = _lang


def language_entry(language_code: str) -> Language | None:
    """Idioma canônico ou None se desconhecido."""
    return _BY_LANGUAGE.get(language_code)


def locale_entry(locale_code: str) -> Locale | None:
    """Localidade canônica (procura em todos os idiomas) ou None."""
    for lang in LANGUAGES:
        for locale in lang.locales:
            if locale.code == locale_code:
                return locale
    return None


def describe_pair(language_code: str, locale_code: str | None) -> str:
    """Descrição leiga do par, para prompts e telas.

    Ex.: ("pt", "pt-br") -> "português do Brasil (language_code=pt,
    locale_code=pt-br)". Par só de idioma -> "japonês (language_code=ja)".
    """
    lang = language_entry(language_code)
    lang_name = lang.name if lang else language_code
    if locale_code:
        loc = locale_entry(locale_code)
        loc_name = loc.name if loc else locale_code
        return f"{loc_name} (language_code={language_code}, locale_code={locale_code})"
    return f"{lang_name} (language_code={language_code})"
