"""Contrato de idioma (Emenda 014): catálogo, normalização, validação."""

import pytest

from packages.multilingual import (
    LANGUAGES,
    LanguageError,
    describe_pair,
    language_entry,
    locale_entry,
    normalize_language_pair,
    normalize_language_tag,
    validate_pair,
)


class TestCatalog:
    def test_catalog_has_languages_with_locales(self):
        assert len(LANGUAGES) >= 10
        pt = language_entry("pt")
        assert pt is not None and pt.name == "Português"
        assert pt.default_locale is not None
        assert pt.default_locale.code == "pt-br"

    def test_no_language_uses_region_as_code(self):
        # contrato: language_code nunca é "pt-br"
        for lang in LANGUAGES:
            assert "-" not in lang.code
            for locale in lang.locales:
                assert locale.code.startswith(lang.code + "-")

    def test_locale_entry_lookup(self):
        assert locale_entry("pt-br") is not None
        assert locale_entry("pt-BR") is None  # catálogo só guarda canônico
        assert locale_entry("xx-xx") is None


class TestNormalizeTag:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("pt-BR", ("pt", "pt-br")),
            ("pt_BR", ("pt", "pt-br")),
            ("PT-br", ("pt", "pt-br")),
            (" pt-br ", ("pt", "pt-br")),
            ("en-US", ("en", "en-us")),
            ("en_US", ("en", "en-us")),
            ("pt", ("pt", None)),
            ("english", ("en", None)),
            ("brazilian portuguese", ("pt", None)),
            ("brazilian-portuguese", ("pt", None)),
            ("portuguese", ("pt", None)),
            ("zh-cn", ("zh", "zh-cn")),
        ],
    )
    def test_normalizes_aliases(self, raw, expected):
        assert normalize_language_tag(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["xx", "pt-xx", "pt-português", "en-pt", "klingon", ""],
    )
    def test_rejects_unknown_with_explicit_error(self, raw):
        with pytest.raises(LanguageError):
            normalize_language_tag(raw)


class TestNormalizePair:
    def test_pair_canonical(self):
        assert normalize_language_pair("pt", "pt-br") == ("pt", "pt-br")

    def test_pair_normalizes_region(self):
        assert normalize_language_pair("pt", "BR") == ("pt", "pt-br")
        assert normalize_language_pair("en", "US") == ("en", "en-us")

    def test_pair_language_only(self):
        assert normalize_language_pair("ja", None) == ("ja", None)
        assert normalize_language_pair("ja", "") == ("ja", None)

    def test_locale_without_language_is_error(self):
        with pytest.raises(LanguageError):
            normalize_language_pair(None, "pt-br")
        with pytest.raises(LanguageError):
            normalize_language_pair("", "pt-br")

    def test_incompatible_pair_is_error(self):
        with pytest.raises(LanguageError):
            normalize_language_pair("pt", "en-us")
        with pytest.raises(LanguageError):
            normalize_language_pair("ja", "br")

    def test_unknown_language_is_error(self):
        with pytest.raises(LanguageError):
            normalize_language_pair("klingon", None)


class TestValidatePair:
    def test_accepts_canonical(self):
        validate_pair("pt", "pt-br")
        validate_pair("en", None)

    def test_rejects_legacy_compound_language(self):
        # language_code="pt-br" viola o contrato
        with pytest.raises(LanguageError):
            validate_pair("pt-br", None)


class TestDescribe:
    def test_describe_pair_leigo(self):
        assert "Português do Brasil" in describe_pair("pt", "pt-br")
        assert "language_code=pt" in describe_pair("pt", "pt-br")
        assert "locale_code=pt-br" in describe_pair("pt", "pt-br")

    def test_describe_language_only(self):
        assert "Japonês" in describe_pair("ja", None)
