"""Multilingual contract (Emenda 014): language_code + locale_code.

Source of truth for languages/locales in the HIL. Idioma é dimensão do
CONTEÚDO — nunca da plataforma. Nunca `language_code="pt-br"`: o
language_code é o idioma canônico ("pt") e o locale_code é a localidade
("pt-br").
"""

from packages.multilingual.catalog import (
    LANGUAGES,
    describe_pair,
    language_entry,
    locale_entry,
)
from packages.multilingual.normalize import (
    LanguageError,
    normalize_language_pair,
    normalize_language_tag,
    validate_pair,
)

__all__ = [
    "LANGUAGES",
    "LanguageError",
    "describe_pair",
    "language_entry",
    "locale_entry",
    "normalize_language_pair",
    "normalize_language_tag",
    "validate_pair",
]
