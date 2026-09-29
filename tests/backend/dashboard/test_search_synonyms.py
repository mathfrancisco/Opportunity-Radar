"""Unit tests for the synonym dictionary (card F17-03), no database needed."""

from __future__ import annotations

from opportunity_radar.dashboard.search_synonyms import synonym_variants


def test_plain_token_gets_a_synonym_variant() -> None:
    variants = synonym_variants("developer senior")
    assert "desenvolvedor senior" in variants
    assert "engineer senior" in variants


def test_quoted_phrase_is_never_substituted() -> None:
    variants = synonym_variants('"senior developer"')
    assert variants == ['"senior developer"']


def test_negated_token_is_never_substituted() -> None:
    variants = synonym_variants("engineer -junior")
    assert all("-desenvolvedor" not in variant for variant in variants)
    assert all("-júnior" not in variant for variant in variants)


def test_and_or_keywords_pass_through_untouched() -> None:
    variants = synonym_variants("remoto OR pleno")
    assert "remote OR pleno" in variants
    assert "remoto OR mid" in variants


def test_term_without_synonyms_returns_only_itself() -> None:
    assert synonym_variants("kubernetes") == ["kubernetes"]
