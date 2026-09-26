# CARD F20-34 — Buscas salvas

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-01
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-12](../../38-roadmap-ia-e-busca/fase-17/f17-12-buscas-salvas.md)

## Ajustes da Fase 20

- Sem mudança de escopo. Buscas salvas não usam busca por significado (sem embedding).

## Resultado

O operador salva uma combinação de termo e filtros, e a Visão geral mostra quantas vagas
novas cada busca salva teve desde a última vez que ele a abriu.

## Contexto

Com a busca full-text e os filtros do F20-01 (antigo F17-03), o operador passa a ter consultas que repete
("backend remoto sênior Brasil", "dados pleno LATAM"). Refazer a consulta toda vez é
atrito, e não há como saber o que é novo desde a última visita.

## Escopo

- **Tabela `dashboard.saved_search`:** nome, termo, filtros (JSONB, no mesmo formato da
  URL da Inbox), `last_opened_at`, criação.
- **API:** CRUD em `/saved-searches` e `GET /saved-searches/{id}/new-count` (vagas que
  casam com a busca e foram criadas depois de `last_opened_at`).
- **Inbox:** "Salvar esta busca" a partir do termo e filtros atuais; lista das buscas
  salvas ao lado da busca; abrir uma atualiza `last_opened_at`.
- **Visão geral:** no bloco de decisão, "Buscas salvas com novidade" com o nome e a
  contagem de cada uma que tem vaga nova.

## Fora de escopo

- Notificação por e-mail ou webhook.
- Compartilhar buscas.

## Notas de implementação

- A contagem reusa a mesma função de consulta da Inbox, com filtro extra por
  `created_at > last_opened_at`, para não haver duas definições de "casa com a busca".
- Filtro que deixa de existir (ex.: área renomeada numa versão nova) é ignorado com aviso,
  não quebra a busca salva.

## Critérios de aceite

- [ ] Buscas são salvas, listadas, abertas, renomeadas e removidas.
- [ ] A contagem de novidades usa a mesma consulta da Inbox.
- [ ] A Visão geral mostra as buscas com novidade.

## Verificação

- **CI:** testes de integração do CRUD e da contagem com vagas criadas antes e depois da
  abertura; testes de componente da lista e do botão de salvar.

## Arquivos prováveis

- `migrations/versions/*_saved_search.py`
- `src/opportunity_radar/dashboard/queries.py`, `presentation/http/dashboard.py`
- `apps/web/src/routes/InboxPage.tsx`, `OverviewPage.tsx`

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/dashboard/models.py` | O contexto `dashboard` hoje não tem `models.py` (só `queries.py`, `metrics.py`, `analysis_metrics.py`, `search_filters.py`, `search_synonyms.py` — puramente leitura); criar `SavedSearchModel` (`dashboard.saved_search`), no formato dos outros modelos SQLAlchemy do projeto (`Base` de `opportunity_radar.platform.database`). |
| Criar | `src/opportunity_radar/dashboard/saved_searches.py` | CRUD (criar, listar, abrir, renomear, remover) e `new_count`, reaproveitando `list_opportunity_inbox`/`InboxQuery` de `queries.py`. |
| Alterar | `src/opportunity_radar/dashboard/queries.py` | `InboxQuery` (linha 111-147) não tem filtro por data de criação; adicionar `created_after: datetime \| None = None`, comparado contra `OpportunityModel.created_at`, para a contagem de novidade reusar exatamente `list_opportunity_inbox` (linha 520) em vez de uma segunda definição de "casa com a busca". |
| Criar | `migrations/versions/20260926_0033_saved_search.py` | Cria `dashboard.saved_search` (nome, termo, filtros JSONB, `last_opened_at`, criação). Número indicativo: latest hoje é `20260925_0029`; F20-12/19/23 reservam 0030-0032 — usar 0033 ou o que `alembic heads` indicar. |
| Alterar | `src/opportunity_radar/presentation/http/dashboard.py` | Adicionar `POST/GET/PATCH/DELETE /saved-searches` e `GET /saved-searches/{id}/new-count`, no formato de `list_inbox` (linha 282-336) para montar `InboxQuery` a partir dos filtros salvos. |
| Alterar | `apps/web/src/routes/InboxPage.tsx` | Botão "Salvar esta busca" a partir dos parâmetros atuais de `useSearchParams` (linha 176-197) e a lista de buscas salvas ao lado da busca. |
| Alterar | `apps/web/src/routes/OverviewPage.tsx` | Bloco "Decisão de hoje" (`PendingDecisions`, linha 420-475) ganha "Buscas salvas com novidade", no mesmo estilo dos indicadores já ali (ex.: `followUpsDue`, linha 453). |
| Criar | `apps/web/src/features/saved-searches/api.ts` | Cliente HTTP das rotas novas, no formato de `apps/web/src/features/sources/api.ts`. |
| Criar | `apps/web/src/features/saved-searches/useSavedSearches.ts` | Hooks React Query, no formato de `useSources.ts`. |

## Interfaces

```python
# src/opportunity_radar/dashboard/models.py
class SavedSearchModel(Base):
    __tablename__ = "saved_search"
    __table_args__ = ({"schema": "dashboard"},)

    id: Mapped[UUID]
    name: Mapped[str]
    term: Mapped[str | None]
    filters: Mapped[dict[str, Any]]  # JSONB, mesmo formato dos parâmetros da URL da Inbox
    last_opened_at: Mapped[datetime | None]
    created_at: Mapped[datetime]


# src/opportunity_radar/dashboard/saved_searches.py
@dataclass(frozen=True, slots=True)
class SavedSearch:
    id: UUID
    name: str
    term: str | None
    filters: dict[str, Any]
    last_opened_at: datetime | None
    created_at: datetime


def create_saved_search(session: Session, *, name: str, term: str | None, filters: dict[str, Any]) -> SavedSearch: ...
def list_saved_searches(session: Session) -> tuple[SavedSearch, ...]: ...
def rename_saved_search(session: Session, saved_search_id: UUID, *, name: str) -> SavedSearch: ...
def delete_saved_search(session: Session, saved_search_id: UUID) -> None: ...


def open_saved_search(session: Session, saved_search_id: UUID) -> SavedSearch:
    """Atualiza `last_opened_at` para agora e devolve a busca."""


def new_count(session: Session, saved_search: SavedSearch) -> int:
    """`list_opportunity_inbox` com a mesma `InboxQuery` dos filtros salvos, mais
    `created_after=saved_search.last_opened_at`. Filtro desconhecido (área renomeada
    numa versão nova) é ignorado com aviso, não quebra a contagem."""


# src/opportunity_radar/dashboard/queries.py (extensão)
@dataclass(frozen=True, slots=True)
class InboxQuery:
    ...
    created_after: datetime | None = None  # novo: só para "vagas novas desde X"
```

## Passos

1. Escrever os testes de integração do CRUD e da contagem (vagas criadas antes/depois da abertura) antes do código.
2. Criar `src/opportunity_radar/dashboard/models.py` com `SavedSearchModel`.
3. Criar a migração `migrations/versions/20260926_0033_saved_search.py` com `dashboard.saved_search`.
4. Adicionar `created_after` a `InboxQuery` (`queries.py`, linha 111-147) e o filtro correspondente em `list_opportunity_inbox` (linha 520).
5. Criar `src/opportunity_radar/dashboard/saved_searches.py` com o CRUD e `new_count`, convertendo o JSONB `filters` para `InboxQuery` campo a campo, ignorando com aviso qualquer chave que a versão atual do filtro não reconheça.
6. Expor as rotas em `presentation/http/dashboard.py`: `POST /saved-searches`, `GET /saved-searches`, `PATCH /saved-searches/{id}` (renomear/abrir), `DELETE /saved-searches/{id}`, `GET /saved-searches/{id}/new-count`.
7. Criar `apps/web/src/features/saved-searches/api.ts` e `useSavedSearches.ts`.
8. Adicionar "Salvar esta busca" e a lista de buscas salvas a `InboxPage.tsx`, construindo `filters` a partir do próprio `URLSearchParams` já lido ali (linha 176-197).
9. Adicionar "Buscas salvas com novidade" ao bloco "Decisão de hoje" em `OverviewPage.tsx` (`PendingDecisions`, linha 420-475).
10. Escrever o teste do filtro obsoleto (área renomeada) sendo ignorado com aviso em vez de quebrar a busca salva.
11. Rodar os comandos de verificação.

## Testes a escrever

- `tests/backend/dashboard/test_queries.py::test_inbox_query_filters_by_created_after`
- `tests/backend/dashboard/test_saved_searches.py::test_create_list_rename_delete_saved_search`
- `tests/backend/dashboard/test_saved_searches.py::test_open_saved_search_updates_last_opened_at`
- `tests/backend/dashboard/test_saved_searches.py::test_new_count_uses_same_query_as_inbox`
- `tests/backend/dashboard/test_saved_searches.py::test_new_count_counts_only_opportunities_created_after_last_opened`
- `tests/backend/dashboard/test_saved_searches.py::test_unknown_filter_key_is_ignored_with_warning`
- `apps/web/src/features/saved-searches/api.test.ts::salva, lista e abre uma busca`
- `apps/web/src/routes/OverviewPage.test.tsx::mostra buscas salvas com novidade` (se a suíte de `OverviewPage` existir; caso contrário, nota no PR)

## Não fazer

- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI; usar `httpx.MockTransport` ou os servidores falsos de `tests/e2e/`.
- Não adicionar dependência nova sem registrar o motivo no PR.
- Não usar LLM neste card, salvo quando a seção "Ajustes da Fase 20" disser o contrário.

## Como trabalhar este card

1. Ler "Ajustes da Fase 20" primeiro: eles prevalecem sobre o texto herdado.
2. Ler "Arquivos prováveis" e confirmar cada caminho com `ls`/`grep` antes de editar; caminho inexistente vira nota no PR.
3. Escrever primeiro os testes dos critérios de aceite, depois o código.
4. IDs antigos no texto aparecem como `F20-xx (antigo F1x-yy)`; a tabela completa está no README da Fase 20.
5. O que depende do acervo real ("Máquina de referência") é medido fora do CI e colado no PR.

## Comando de verificação

```bash
docker compose -p f20-34 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/dashboard/test_queries.py tests/backend/dashboard/test_saved_searches.py
docker compose -p f20-34 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-34 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
