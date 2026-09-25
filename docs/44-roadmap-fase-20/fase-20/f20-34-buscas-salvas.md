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
docker compose -p f20-34 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-34 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-34 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

Se o card mexer em `apps/web`, rodar também `cd apps/web && npm run check`.

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa e o CI está verde.
