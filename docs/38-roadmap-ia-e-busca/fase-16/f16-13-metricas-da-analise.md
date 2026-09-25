# CARD F16-13 — Métricas da análise na API, na Visão geral e no `doctor`

- **Status:** Implementação integrada (PR #18); aceite documental pendente
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-03
- **Bloqueia:** Milestone O
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §9

## Resultado

O operador vê, sem abrir log, quanto a análise está custando, quanto falha e quanto está
atrasada, e o `doctor` diz se o modelo está na GPU.

## Contexto inicial (antes da implementação)

O F16-03 grava o custo de cada análise, mas número por linha não responde "o p95 da última
semana subiu?". A Visão geral já tem o padrão de métricas por fonte com linha de apoio no
bloco de operação; a análise merece o mesmo.

## Escopo

- `GET /analysis-metrics?window=24h|7d`: p50, p95 e p99 de `total_ms`; médias de
  `prompt_tokens` e `output_tokens`; taxa por `failure_code`; taxa de reaproveitamento
  (F16-08); tamanho da fila pendente; carga média (`load_ms`). Janela sem análises devolve
  `null`, nunca zero.
- **Visão geral:** linha de apoio no bloco "Operação" — "Análise: p50 X s · p95 Y s · Z na
  fila · W% falhas (7 dias)", com link para o detalhe.
- **`doctor`:** versão do servidor, modelos carregados com `size_vram` × `size` (F16-01),
  `keep_alive` efetivo, fila pendente, e aviso quando o p95 de 24 h passa da meta da SPEC
  §3.2.
- Tipos e parser no frontend, com o mesmo tratamento de "indisponível".

## Fora de escopo

- Alertas por webhook da análise (o canal de alerta atual é de fontes).
- Painel histórico com gráficos.

## Notas de implementação

- Percentis com `percentile_cont` no Postgres, sobre linhas com `total_ms` não nulo.
- A janela de 7 dias atravessa a troca de modelo; agrupar por `model_id` e mostrar o
  modelo atual na Visão geral.

## Critérios de aceite

- [ ] O endpoint devolve os agregados por janela, com `null` em janela vazia.
- [ ] A Visão geral mostra a linha de apoio da análise.
- [ ] O `doctor` informa GPU, fila e p95 contra a meta.

## Verificação

- **CI:** teste de integração do endpoint com análises fixas de custos conhecidos (conferir
  percentis) e janela vazia; teste de parser no frontend; E2E conferindo a forma da
  resposta.

## Arquivos prováveis

- `src/opportunity_radar/dashboard/queries.py`, `presentation/http/dashboard.py`
- `scripts/doctor.py`
- `apps/web/src/routes/OverviewPage.tsx`, `apps/web/src/features/dashboard/`
