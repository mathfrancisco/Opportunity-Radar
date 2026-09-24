# CARD F17-12 — Buscas salvas

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-03
- **Bloqueia:** Nenhum
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §10

## Resultado

O operador salva uma combinação de termo e filtros, e a Visão geral mostra quantas vagas
novas cada busca salva teve desde a última vez que ele a abriu.

## Contexto

Com a busca full-text e os filtros do F17-03, o operador passa a ter consultas que repete
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
