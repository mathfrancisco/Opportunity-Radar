# CARD F20-74 — Coletor Workday: parar no `total` anunciado (cap de 2000)

- **Status:** Feito (2026-09-29) — correção e teste de regressão; re-execução real da
  Accenture pendente (ver Evidência).
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** C — Busca: cobertura e precisão
- **Depende de:** F20-28
- **Origem:** Accenture (`accenture/AccentureCareers`, pod `wd103`) terminou `PARTIAL`
  com `PARSER_SCHEMA_CHANGED` após 1997 itens
  ([`mapa-carreira-vs-catalogo-2026-09-28.md`](../evidencias/mapa-carreira-vs-catalogo-2026-09-28.md)).

## Causa raiz (medida no endpoint real)

`POST .../wday/cxs/accenture/AccentureCareers/jobs`: a página de `offset=0` traz
`total=2000` (Workday limita a 2000); páginas seguintes trazem `total=0`; o último trecho
real é `offset=1990` com 10 itens; a partir de `offset=2000` o Workday **reinicia do
início** (mesma primeira página de `offset=0`, `total=2000`). O coletor ignorava `total`,
fazia mais um pedido em `offset=2000`, via a página repetida e levantava
`PARSER_SCHEMA_CHANGED`. Não era mudança de esquema: era o fim do board.

## Correção

`src/opportunity_radar/acquisition/workday.py`: lê `total` (> 0) da página de `offset=0`
e encerra sem novo pedido quando `offset >= total`, anunciando os itens lidos. A guarda de
página repetida continua (repetição com `total` ainda não atingido segue sendo erro).
Retomada com cursor > 0 não conhece `total`; comportamento anterior preservado.

## Critérios de aceite

- [x] Fixture reproduz o wrap do cap (total 60, páginas 20/20/20, offset 60 volta à
      primeira página): coleta 60 itens únicos, pedidos `[0, 20, 40]`,
      `items_announced == 60` — `test_stops_at_the_announced_total_when_workday_wraps_past_the_cap`.
- [x] Teste antigo de página repetida com `total` não atingido continua levantando erro.
- [ ] Re-execução da Accenture na `f20manual` com `SUCCEEDED`: **não executada** — copiar
      o coletor corrigido para o container do worker foi negado pelo classificador da
      sessão. Executar após rebuild/`docker cp` na `f20manual`.
