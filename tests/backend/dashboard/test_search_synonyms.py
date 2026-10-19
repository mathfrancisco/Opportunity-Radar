"""Unit tests for the synonym dictionary (card F17-03), no database needed."""

from __future__ import annotations

from opportunity_radar.dashboard.search_synonyms import synonym_groups, synonym_variants


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


def test_groups_have_one_entry_per_plain_token() -> None:
    groups = synonym_groups("desenvolvedor dados")
    assert groups is not None
    assert len(groups) == 2
    assert groups[0][0] == "desenvolvedor"
    assert {"developer", "engineer"} <= set(groups[0])
    assert set(groups[1]) == {"dados", "data"}


def test_groups_keep_unknown_tokens_alone() -> None:
    assert synonym_groups("kubernetes dados") == [["kubernetes"], ["dados", "data"]]


def test_groups_are_none_for_quotes_negation_or_and_long_queries() -> None:
    assert synonym_groups('"desenvolvedor dados"') is None
    assert synonym_groups("desenvolvedor -dados") is None
    assert synonym_groups("remoto OR pleno") is None
    assert synonym_groups("remoto or pleno") is None
    assert synonym_groups(" ".join(["dados"] * 9)) is None
    assert synonym_groups(" ".join(["dados"] * 8)) is not None
