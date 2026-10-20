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


def test_groups_only_cover_tokens_with_synonyms() -> None:
    split = synonym_groups("desenvolvedor dados")
    assert split is not None
    groups, rest = split
    assert len(groups) == 2
    assert groups[0][0] == "desenvolvedor"
    assert {"developer", "engineer"} <= set(groups[0])
    assert set(groups[1]) == {"dados", "data"}
    assert rest == ""


def test_remaining_tokens_are_joined_in_order() -> None:
    split = synonym_groups("engenheiro de kubernetes")
    assert split is not None
    groups, rest = split
    assert len(groups) == 1
    assert rest == "de kubernetes"


def test_groups_are_none_without_synonyms_quotes_negation_or_and_long_queries() -> None:
    assert synonym_groups("kubernetes") is None
    assert synonym_groups('"desenvolvedor dados"') is None
    assert synonym_groups("desenvolvedor -dados") is None
    assert synonym_groups("remoto OR pleno") is None
    assert synonym_groups("remoto or pleno") is None
    assert synonym_groups(" ".join(["dados"] * 9)) is None
    assert synonym_groups(" ".join(["dados"] * 8)) is not None


def test_punctuation_glued_to_a_token_still_finds_its_synonyms() -> None:
    split = synonym_groups("desenvolvedor dados,")
    assert split is not None
    groups, rest = split
    assert set(groups[1]) == {"dados", "data"}
    assert rest == ""
    assert "data, desenvolvedor" not in synonym_variants("dados, desenvolvedor")
    assert "data desenvolvedor" in synonym_variants("dados, desenvolvedor")


def test_filler_concept_is_dropped_next_to_another_term() -> None:
    split = synonym_groups("vaga engenheiro")
    assert split is not None
    groups, rest = split
    assert [group[0] for group in groups] == ["engenheiro"]
    assert rest == ""

    split = synonym_groups("vaga python")
    assert split is not None
    groups, rest = split
    assert groups == []
    assert rest == "python"


def test_filler_concept_alone_is_kept() -> None:
    split = synonym_groups("vaga")
    assert split is not None
    groups, rest = split
    assert set(groups[0]) == {"vaga", "job"}
    assert rest == ""
