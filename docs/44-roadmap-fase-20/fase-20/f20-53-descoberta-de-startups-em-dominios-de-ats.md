# CARD F20-53 — Descoberta de startups em domínios de ATS via Tavily

- **Status:** Feito — 21 fontes importadas e habilitadas na stack real em 2026-09-29 (probe `PASSED`, 137 habilitadas no total; `docs/44-roadmap-fase-20/evidencias/rebuild-stack-real-2026-09-29.md` §7). `startup_discovery.py` + `scripts/discover_startups.py`; execução real na `f20manual` em 2026-09-29 (20 créditos Tavily, 23 propostas ativadas e coletadas, `evidencias/startups-f20-53-2026-09-29.md`)
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-44, F20-46, F20-27, F20-36
- **Origem:** [SPEC 45](../../45-spec-descoberta-startups.md); pesquisa
  [`docs/pesquisas/descoberta-startups-ats.md`](../../pesquisas/descoberta-startups-ats.md);
  pedido do usuário em 2026-09-28 (interesse em startups no board, alternativa viável a
  F20-51/F20-52 fechados não viável).

## Resultado

Busca Tavily por sinal de startup (`"Y Combinator"`, `"YC "+batch, "seed stage"`,
`"Series A"`) restrita aos domínios de ATS já suportados (Ashby, Greenhouse, Lever,
Workable, Teamtailor) alimenta a mesma fila de proposta/homologação que a busca geral do
F20-44/F20-46 já alimenta. Nenhuma chamada a `wellfound.com`, `ycombinator.com/jobs` ou
`workatastartup.com`.

## Contexto

Piloto de viabilidade (4 buscas, ~5 créditos Tavily) mediu ~95% de candidatos novos
frente ao catálogo atual e maior precisão de sinal quando a query cita marca nomeada
(YC/"Y Combinator") do que quando cita só estágio (`"seed stage"`/`"Series A"` sozinhos,
que trouxe um falso positivo grosseiro). Ver a pesquisa citada em "Origem" para a tabela
completa.

## Escopo

- Nova função de montagem de query em `acquisition/tavily.py` (ou módulo próprio,
  `acquisition/startup_discovery.py`): combina um termo de startup configurado com
  `include_domains` restrito aos domínios de ATS já suportados — reusa
  `TavilySearchCollector` existente (F20-44), não cria coletor novo.
- Cada termo carrega uma força (`forte` para marca nomeada YC/"Y Combinator"+batch,
  `fraco` para estágio sem marca) que fica no `metadata` do `CollectedItem`, para o
  F20-54 decidir a marcação de evidência.
- Dedupe por empresa (não só por URL de board): quando duas propostas do mesmo ciclo
  apontam nomes normalizados iguais em ATS diferentes (ex.: mesma empresa em Lever e
  Workable, achado no piloto), registrar como uma única proposta com os dois boards como
  evidência, não duas propostas concorrentes.
- Reusa `propose_from_tavily_evidence` (F20-46) para a criação de proposta — mesma
  idempotência, mesmo `discovery_via`, com um valor distinto (`"tavily_startup_search"`)
  para diferenciar da busca geral do F20-44 nas métricas de rendimento por via.
- Cadência e número de queries por ciclo entram no mesmo `TavilyBudgetGuard` (F20-43) —
  sem orçamento novo, sem teto próprio.

## Fora de escopo

- Qualquer chamada a Wellfound, YC/WaaS ou a qualquer domínio fora dos ATS já suportados.
- Marcação "startup" no `company_radar.company` e filtro de UI — F20-54.
- Homologar ou habilitar a fonte proposta — segue a fila existente (F20-25).
- Coletor novo de ATS.

## Critérios de aceite

- [x] Query combina termo de startup configurado com `include_domains` restrito aos
      domínios de ATS já suportados; nunca inclui domínio fora dessa lista.
- [x] Força do sinal (`forte`/`fraco`) fica registrada no `metadata` do `CollectedItem`
      por termo usado na query.
- [x] Duas propostas do mesmo ciclo apontando para o mesmo nome normalizado de empresa em
      ATS diferentes resultam em uma única proposta com os dois boards como evidência.
- [x] Proposta criada por esta via registra `discovery_via="tavily_startup_search"`,
      distinto da busca geral do F20-44 (`"tavily_search"`).
- [x] Nenhuma requisição de rede desta rotina alcança `wellfound.com`,
      `ycombinator.com` ou `workatastartup.com` (teste de allowlist de domínio).

## Verificação

- **CI:** fixtures de resposta `/search` da Tavily via `httpx.MockTransport` cobrindo
  termo forte/fraco, dedupe cross-ATS por nome normalizado, e o teste de allowlist de
  domínio (nenhuma URL de resultado fora dos domínios de ATS suportados é aceita mesmo se
  a Tavily devolvê-la).
- **Máquina de referência:** sem chamada real à Tavily.

## Arquivos prováveis

- `src/opportunity_radar/acquisition/tavily.py` ou novo
  `src/opportunity_radar/acquisition/startup_discovery.py`
- `src/opportunity_radar/acquisition/proposals.py`
- `tests/backend/acquisition/test_startup_discovery.py` (novo)

## Não fazer

- Não implementar coletor, sonda ou integração de descoberta para Wellfound, YC ou WaaS.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não habilitar fonte sem passar pelo gate de homologação.
- Não fazer chamada real a boards, Groq ou Tavily no CI.
- Não criar orçamento de créditos separado do `TavilyBudgetGuard` existente (F20-43).

## Comando de verificação

```bash
docker compose -p f20-53 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/acquisition/test_startup_discovery.py
docker compose -p f20-53 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-53 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados com evidência, o comando de verificação passa
e o CI está verde.

## Evidência de entrega (2026-09-29)

Código: `src/opportunity_radar/acquisition/startup_discovery.py` (busca, dedupe, validação,
proposta), `scripts/discover_startups.py` (execução manual, teto `--max-credits`, padrão 20),
`propose_from_tavily_evidence(..., discovery_via=...)` em `service.py`,
`detect_ats_board` estendido a Workable/Teamtailor/`job-boards.greenhouse.io`
(`tavily.py`), `probe_direct_ats(..., slugs=, only_ats=)` (`limited_discovery.py`).
Testes em `tests/backend/acquisition/test_startup_discovery.py` (fakes, sem rede):

| Critério | Teste |
| --- | --- |
| Query só com domínios de ATS suportados | `test_query_combines_term_with_supported_ats_domains_only`, `test_domain_group_outside_supported_ats_is_refused` |
| Força `forte`/`fraco` no `metadata` | `test_signal_strength_and_term_are_recorded_in_item_metadata_per_term` |
| Mesma empresa em ATS diferentes = uma proposta, dois boards de evidência | `test_same_company_in_two_ats_becomes_one_candidate_with_both_boards`, `test_cross_ats_company_yields_single_proposal_with_both_boards_as_evidence` (a proposta é o board validado; todos os boards vão em `startup_boards`) |
| `discovery_via="tavily_startup_search"` | `test_validated_startup_becomes_inert_proposal_tagged_startup_search` |
| Nenhuma requisição a wellfound/ycombinator/workatastartup | `test_results_outside_supported_ats_domains_are_dropped_even_if_tavily_returns_them`, `test_no_request_of_the_routine_reaches_forbidden_hosts` |
| Orçamento F20-43 compartilhado | `test_queries_share_the_tavily_budget_and_stop_at_the_ceiling` |

Execução real: `evidencias/startups-f20-53-2026-09-29.md`.
