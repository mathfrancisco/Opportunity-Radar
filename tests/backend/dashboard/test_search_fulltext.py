"""Full-text search over the Inbox (card F17-03, SPEC 37 §10).

One test per acceptance criterion. All exercise `search_document`/`websearch_to_tsquery`
in Postgres, so they run only against the isolated CI database, like the rest of
`tests/backend/dashboard/test_queries.py`.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from opportunity_radar.dashboard.queries import (
    InboxQuery,
)
from opportunity_radar.dashboard.queries import list_opportunity_inbox as _list_opportunity_inbox
from opportunity_radar.platform.database import create_database_engine

from .test_queries import _company, _opportunity

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("RUN_DATABASE_INTEGRATION") != "1",
        reason="database integration is enabled only in the isolated CI database",
    ),
]

NOW = datetime.now(UTC)
OWNER_SUB = "user-search-fulltext"


def list_opportunity_inbox(session: Session, query: InboxQuery):
    return _list_opportunity_inbox(session, query, owner_sub=OWNER_SUB)


def _session() -> Session:
    engine = create_database_engine(os.environ["DATABASE_URL"])
    return Session(engine)


def test_term_present_only_in_description_is_found() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session,
            company,
            title="Software Engineer",
            published_at=NOW,
            description="Requires strong Kubernetes experience running production clusters.",
        )
        _opportunity(session, company, title="Unrelated Analyst", published_at=NOW)
        session.commit()

        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="Kubernetes")
        )
        assert [item.opportunity_id for item in found.items] == [target.id]


def test_search_ignores_accent_and_matches_plural_from_singular() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session,
            company,
            title="Engenheira de Dados Júnior",
            published_at=NOW,
            description="Vaga para atuação remota, foco em pipelines de dados.",
        )
        session.commit()

        no_accent = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="Junior")
        )
        assert [item.opportunity_id for item in no_accent.items] == [target.id]

        singular_from_plural = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="pipeline")
        )
        assert [item.opportunity_id for item in singular_from_plural.items] == [target.id]


def test_domain_synonyms_widen_the_search() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session,
            company,
            title="Desenvolvedor Backend Sênior",
            published_at=NOW,
        )
        session.commit()

        by_synonym = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="developer senior")
        )
        assert [item.opportunity_id for item in by_synonym.items] == [target.id]


def test_filters_combine_with_the_search_term() -> None:
    with _session() as session:
        company = _company(session, "normal")
        matching = _opportunity(
            session,
            company,
            title="Data Engineer",
            published_at=NOW,
            work_mode="REMOTE",
            description="Own the pipeline that feeds analytics dashboards.",
        )
        _opportunity(
            session,
            company,
            title="Data Engineer",
            published_at=NOW,
            work_mode="ONSITE",
            description="Own the pipeline that feeds analytics dashboards.",
        )
        session.commit()

        combined = list_opportunity_inbox(
            session,
            InboxQuery(company_id=company.id, search="pipeline", work_mode="REMOTE"),
        )
        assert [item.opportunity_id for item in combined.items] == [matching.id]


def test_title_match_ranks_above_description_only_match() -> None:
    with _session() as session:
        company = _company(session, "normal")
        title_match = _opportunity(
            session, company, title="Kubernetes Platform Engineer", published_at=NOW
        )
        description_match = _opportunity(
            session,
            company,
            title="Backend Engineer",
            published_at=NOW,
            description="Some Kubernetes exposure is a plus, not required.",
        )
        session.commit()

        ranked = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="Kubernetes")
        )
        assert [item.opportunity_id for item in ranked.items] == [
            title_match.id,
            description_match.id,
        ]


@pytest.mark.parametrize(
    ("title", "queries"),
    [
        ("Gestão de Produto", ("gestão", "gestao")),
        ("Análise de Dados", ("análise", "analise")),
        ("Ciência de Dados", ("ciência de dados", "ciencia de dados")),
        ("Programação Backend", ("programação", "programacao")),
        ("Ação Social", ("ação", "acao")),
        ("Gestao sem acento", ("gestão", "gestao")),
        ("Analista Júnior", ("júnior", "junior")),
        ("Engenheiro Sênior", ("sênior", "senior")),
    ],
)
def test_accented_and_plain_queries_find_the_same_title(
    title: str, queries: tuple[str, ...]
) -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(session, company, title=title, published_at=NOW)
        session.commit()

        for query in queries:
            found = list_opportunity_inbox(
                session, InboxQuery(company_id=company.id, search=query)
            )
            assert [item.opportunity_id for item in found.items] == [target.id], query


def test_accented_phrase_and_negation_keep_their_semantics() -> None:
    with _session() as session:
        company = _company(session, "normal")
        ciencia_de_dados = _opportunity(
            session, company, title="Ciência de Dados", published_at=NOW
        )
        _opportunity(session, company, title="Dados de Ciência", published_at=NOW)
        estagio = _opportunity(
            session, company, title="Engenharia de Dados Estágio", published_at=NOW
        )
        pleno = _opportunity(
            session, company, title="Engenharia de Dados Pleno", published_at=NOW
        )
        session.commit()

        def ids(search: str) -> list:
            found = list_opportunity_inbox(
                session, InboxQuery(company_id=company.id, search=search)
            )
            return [item.opportunity_id for item in found.items]

        assert ids('"ciência de dados"') == [ciencia_de_dados.id]
        negated = ids("dados -estágio")
        assert pleno.id in negated
        assert estagio.id not in negated


@pytest.mark.parametrize("term", ["ção", "-", '""', "- ção"])
def test_operator_only_or_accent_only_queries_do_not_raise(term: str) -> None:
    with _session() as session:
        company = _company(session, "normal")
        session.commit()

        list_opportunity_inbox(session, InboxQuery(company_id=company.id, search=term))


@pytest.mark.parametrize(
    ("query", "title"),
    [
        ("desenvolvedor remoto", "Developer Remote"),
        ("engenheiro junior", "Junior Engineer"),
        ("dados remoto", "Data Remote"),
        ("desenvolvedor dados", "Data Developer"),
        ("vaga dados", "Data Job"),
    ],
)
def test_two_concept_bilingual_queries_find_the_translated_title(
    query: str, title: str
) -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(session, company, title=title, published_at=NOW)
        _opportunity(session, company, title="Unrelated Analyst", published_at=NOW)
        session.commit()

        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search=query)
        )
        assert target.id in [item.opportunity_id for item in found.items]


def test_synonym_groups_require_every_concept() -> None:
    with _session() as session:
        company = _company(session, "normal")
        both = _opportunity(session, company, title="Data Developer", published_at=NOW)
        only_dev = _opportunity(
            session, company, title="Backend Developer", published_at=NOW
        )
        only_data = _opportunity(
            session, company, title="Data Analyst", published_at=NOW
        )
        session.commit()

        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="desenvolvedor dados")
        )
        ids = [item.opportunity_id for item in found.items]
        assert both.id in ids
        assert only_dev.id not in ids
        assert only_data.id not in ids


def test_quoted_phrase_and_negation_do_not_expand_across_concepts() -> None:
    with _session() as session:
        company = _company(session, "normal")
        data_developer = _opportunity(
            session, company, title="Data Developer", published_at=NOW
        )
        desenvolvedor_dados = _opportunity(
            session, company, title="Desenvolvedor de Dados", published_at=NOW
        )
        session.commit()

        def ids(search: str) -> list:
            found = list_opportunity_inbox(
                session, InboxQuery(company_id=company.id, search=search)
            )
            return [item.opportunity_id for item in found.items]

        quoted = ids('"desenvolvedor de dados"')
        assert desenvolvedor_dados.id in quoted
        assert data_developer.id not in quoted
        # Negation stays literal (current websearch_to_tsquery path): `-dados` excludes
        # the Portuguese title; it is not widened to the synonym "data".
        negated = ids("desenvolvedor -dados")
        assert desenvolvedor_dados.id not in negated


@pytest.mark.parametrize(
    ("query", "title", "description"),
    [
        (
            "desenvolvedor de dados",
            "Data Developer",
            "Build pipelines for the analytics platform with the product team.",
        ),
        (
            "engenheiro de software",
            "Software Engineer",
            "Design and build backend services for a growing team.",
        ),
        (
            "head of data",
            "Head de Dados",
            "Lidera a area de dados e a estrategia de analytics da empresa.",
        ),
    ],
)
def test_stopword_of_one_dictionary_does_not_become_required(
    query: str, title: str, description: str
) -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session, company, title=title, published_at=NOW, description=description
        )
        session.commit()

        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search=query)
        )
        assert target.id in [item.opportunity_id for item in found.items]


def test_mixed_rest_keeps_its_content_word_required() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(
            session, company, title="Kubernetes Engineer", published_at=NOW
        )
        other = _opportunity(session, company, title="Software Engineer", published_at=NOW)
        session.commit()

        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="engenheiro de kubernetes")
        )
        ids = [item.opportunity_id for item in found.items]
        assert target.id in ids
        assert other.id not in ids


@pytest.mark.parametrize(
    ("query", "title"),
    [
        ("desenvolvedor dados,", "Data Developer"),
        ("vaga engenheiro", "Software Engineer"),
        ("vaga python", "Python Developer"),
    ],
)
def test_punctuation_and_filler_words_do_not_narrow_the_search(
    query: str, title: str
) -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(session, company, title=title, published_at=NOW)
        _opportunity(session, company, title="Unrelated Analyst", published_at=NOW)
        session.commit()

        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search=query)
        )
        ids = [item.opportunity_id for item in found.items]
        assert target.id in ids


def test_one_dictionary_stopword_rest_raises_no_notice() -> None:
    with _session() as session:
        company = _company(session, "normal")
        target = _opportunity(session, company, title="Data Developer", published_at=NOW)
        session.commit()

        notices: list[str] = []
        driver_connection = session.connection().connection.driver_connection
        driver_connection.add_notice_handler(lambda diag: notices.append(diag.message_primary))
        found = list_opportunity_inbox(
            session, InboxQuery(company_id=company.id, search="desenvolvedor de dados")
        )
        assert target.id in [item.opportunity_id for item in found.items]
        assert notices == []
