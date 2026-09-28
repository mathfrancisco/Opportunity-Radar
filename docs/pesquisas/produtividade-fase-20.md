# Relatório de produtividade e custo — Fase 20 (F20-49)

- **Status:** Metas pré-registradas e baseline (T0) preenchidos com dados reais; janela
  de 7 dias **em andamento**, fecha em 2026-10-05 — resultado (T7) e veredicto de cada
  meta ficam **inconclusivos** até lá (ver "Não fazer" do card: nada de amostra
  insuficiente é declarado como ganho ou perda).
- **Card:** [F20-49](../44-roadmap-fase-20/fase-20/f20-49-relatorio-de-produtividade.md)
- **Depende de:** F20-47 (percurso E2E), F20-48 (upgrade de banco populado)
- **Fontes de dado:** [F17-01](baseline-f17-01.md), F20-35 (mapa de cobertura e
  rendimento), F20-20 (métricas de IA no `/analysis-metrics`), F20-43 (orçamento de
  créditos Tavily), F20-21 (baseline real no Groq)
- **Registrado em:** 2026-09-27, antes do fim da janela — as metas abaixo existiam
  antes de qualquer número de T7 ser olhado, como o card pede ("registrar metas antes
  de começar").

## 1. Metas pré-registradas (antes de medir T7)

| Métrica | Meta | Por quê esse número |
| --- | --- | --- |
| Vagas úteis novas / dia | ≥ 1 (≥ 7 na janela de 7 dias) | `useful_yield.new_unique_opportunities` no T0 é 0 numa janela de 2 execuções manuais; qualquer valor positivo sustentado ao longo de 7 dias já é sinal de fluxo real, não um alvo agressivo. |
| Análises de IA concluídas / dia | ≥ 1 análise/dia (sem exigir volume alto — quota diária de tokens é o teto real) | Card F20-21 já mostra 50 análises reais consumindo ~169.798 dos ~170.000 tokens/dia configurados num único dia — a meta aqui é "o fluxo automático produz análises todo dia", não throughput. |
| Taxa de fallback (Groq) | < 5 % | Meta do card F20-49 (texto do "Passos"), consistente com o bloco `ai.by_model[].fallback_rate` do F20-20. |
| Taxa de 429 (rate limit) | < 2 % | Meta do card F20-49; corresponde a `ai.by_model[].rate_limited_rate`. |
| `json_valid_rate` (saída estruturada válida) | ≥ 99 % | Baseline F20-21 mediu 50/50 `AI_COMPLETED` (100 %) num conjunto de avaliação fixo; a meta de produção é ligeiramente mais tolerante a variação real de entrada. |
| Créditos Tavily gastados / dia (plano gratuito, 1.000/mês ⇒ ~33/dia) | ≤ 33 créditos/dia em média na janela | Orçamento do plano gratuito dividido pelos dias do mês; F20-43 já impõe um teto por execução (`tavily_credit_budget_per_run`), a meta aqui é sobre o agregado da janela, não por execução. |
| Erros por tipo (rede, 429, timeout, `invalid_output`, orçamento Tavily esgotado) | Nenhum tipo dominante sem causa identificada | Sem meta numérica — o card pede categorizar, não uma taxa-alvo. |
| Cobertura (`company_coverage_funnel`) | Sem regressão frente ao T0 (`endpoint_discovered` ≥ 220, `homologated` não regride) | A janela de 7 dias é sobre operação, não sobre expansão de catálogo; uma queda indicaria uma fonte quebrada, não falta de trabalho de expansão. |

## 2. Baseline (T0) — dados reais, sem simulação

### 2.1 Busca e cobertura (F20-35 / F17-01)

Snapshot real de `GET /search-metrics?window=7d` (pilha `f20real`, F20-35), salvo em
[`f20-search-metrics-baseline-2026-09-26.json`](../44-roadmap-fase-20/evidencias/f20-search-metrics-baseline-2026-09-26.json):

| Métrica | T0 (2026-09-27T00:52:16Z) |
| --- | --- |
| Execuções na janela (`coverage.runs`) | 2 |
| Itens vistos / persistidos / duplicados | 38 / 19 / 19 |
| Vagas novas únicas (`useful_yield.new_unique_opportunities`) | 0 |
| Empresas catalogadas (`canonical_companies_total`) | 220 |
| Empresas com endpoint descoberto | 220 |
| Empresas homologadas | 0 |
| Empresas com ATS conhecido | 47 |
| `yield_per_100_requests` | 0 |

Esta janela é a mesma aberta pelo F20-35 (não uma segunda janela concorrente medindo um
período diferente): início real `2026-09-27T00:52:16.424759Z`, fim previsto
`2026-10-05`. O T0 é baixo porque as duas execuções da janela até agora foram
verificações pontuais de homologação (F20-28/F20-29), não o scheduler operando em
regime — isso é esperado no início da janela, não uma medição de regime.

### 2.2 Custo de IA (Groq) — baseline de avaliação, não de produção

Fonte: [`baseline-groq-f20-21-2026-09-27.md`](../44-roadmap-fase-20/evidencias/baseline-groq-f20-21-2026-09-27.md)
(50 casos reais do conjunto de avaliação F20-21, um único modelo pinado, sem fallback).

| Métrica | Valor medido |
| --- | --- |
| Modelo | `openai/gpt-oss-120b` (fallback desligado de propósito para a avaliação) |
| Requisições reais | 50 |
| `completed_rate` | 100 % (50/50 `AI_COMPLETED`) |
| Tokens totais | 74.545 (51.541 entrada + 23.004 saída; médias 1.031/460 por caso) |
| Latência `total_ms` | p50 = 1.613 ms, p95 = 2.580 ms |
| Quota de minuto esbarrada | 6 vezes na rodada, sem perda de caso (`--quota-wait-seconds 65`) |
| Consumo do teto diário de tokens | ~169.798 de ~170.000 (`AI_DAILY_TOKENS_SOFT_LIMIT`) no dia UTC 2026-09-27 |

**Limitação registrada:** este número vem de uma rodada de avaliação com fallback
**desligado** (`--model` fixo), não da operação normal com fallback ligado. A taxa de
fallback e a taxa de 429 de produção (as duas metas da tabela acima) precisam vir do
bloco `ai` de `GET /analysis-metrics` observado ao longo da janela de 7 dias, que ainda
não tem volume de chamadas reais de produção acumulado — ver §4.

### 2.3 Créditos Tavily

F20-43 (orçamento de créditos Tavily) está implementado e `SourceRun.credits_used`
existe como coluna auditável (`acquisition.source_run`, ver
`src/opportunity_radar/acquisition/models.py`), mas nenhuma execução real usando o
cliente Tavily (F20-44/45/46) rodou dentro da janela aberta em 2026-09-27 até o
momento deste registro. T0 para créditos Tavily é **0 / sem dado** — não "meta batida",
apenas ainda não medido.

### 2.4 F20-47 / F20-48 — prova de robustez, não de produtividade

F20-47 (percurso E2E com falhas injetadas) e F20-48 (upgrade de banco populado) já
provaram, localmente e com evidência própria, que o pipeline sobrevive a 429/500/saída
inválida do Groq, reinício do worker em coleta e upgrade de banco com histórico sem
duplicar nem perder dados. Isso é uma pré-condição para confiar nos números de T7 (um
sistema que perde dado sob falha invalidaria qualquer contagem de "vagas úteis/dia"),
mas não é, em si, um dado de produtividade — por isso essas duas evidências entram
aqui como base de confiança, não como linha da tabela de resultado.

## 3. Resultado (T0 vs. T7) — preencher ao fim da janela

| Métrica | Meta | T0 (2026-09-27) | T7 (2026-10-05, pendente) | Veredicto |
| --- | --- | --- | --- | --- |
| Vagas úteis novas / dia | ≥ 1/dia | 0 novas em 2 execuções pontuais | **pendente** | inconclusivo — sem T7 |
| Análises de IA concluídas / dia | ≥ 1/dia | não medido em produção (só avaliação) | **pendente** | inconclusivo — sem T7 |
| Taxa de fallback (Groq) | < 5 % | não medido em produção (avaliação rodou com fallback desligado) | **pendente** | inconclusivo — sem T7 |
| Taxa de 429 | < 2 % | 6 esbarrões de minuto em 50 chamadas de avaliação (12 %, contexto de avaliação em rajada, não representativo de produção) | **pendente** | inconclusivo — sem T7 |
| `json_valid_rate` | ≥ 99 % | 100 % (50/50, conjunto de avaliação) | **pendente** | inconclusivo — sem T7 |
| Créditos Tavily / dia | ≤ 33/dia | sem dado (nenhuma execução Tavily na janela até aqui) | **pendente** | inconclusivo — sem T7 |
| Erros por tipo | sem tipo dominante sem causa | nenhum erro sem causa identificada nas evidências disponíveis (F20-31 achou e corrigiu um bug de parser real; não é um erro de operação recorrente) | **pendente** | inconclusivo — sem T7 |
| Cobertura (`company_coverage_funnel`) | sem regressão | `endpoint_discovered=220`, `homologated=0` | **pendente** | inconclusivo — sem T7 |

Nenhuma célula acima foi preenchida com dado sintético ou extrapolado — cada "pendente"
é literal: a amostra ainda não existe porque a janela de 7 dias (F20-35) só termina em
2026-10-05, e não pode ser encurtada sem invalidar a própria medição que o card pede.

## 4. Como preencher T7 (comando exato, restante do trabalho)

Executar em ou depois de **2026-10-05**, contra o ambiente que acumulou a operação real
da janela (não uma pilha isolada nova — precisa ser o mesmo Postgres que rodou desde
2026-09-27):

```bash
# 1. Cobertura e rendimento de busca (mesmo endpoint do T0, mesma janela de 7 dias)
curl -s 'http://localhost:8000/search-metrics?window=7d' | tee \
  docs/44-roadmap-fase-20/evidencias/f20-search-metrics-t7-2026-10-05.json

# 2. Métricas de IA (fallback, 429, json_valid_rate, tokens/dia por modelo — bloco `ai`
#    é uma janela fixa de 24h, então repetir esta chamada uma vez por dia dentro da
#    janela e somar/mediar os 7 snapshots é o que dá o número de 7 dias; um único
#    snapshot em 2026-10-05 só cobre as últimas 24h da janela)
curl -s 'http://localhost:8000/analysis-metrics?window=7d' | tee \
  docs/44-roadmap-fase-20/evidencias/f20-analysis-metrics-t7-2026-10-05.json

# 3. Créditos Tavily gastados na janela (leitura, projeto real permitido apenas para
#    SELECT — não gravar nada fora deste comando)
docker compose -p opportunity-radar exec -T postgres psql -U postgres -d opportunity_radar -c \
  "SELECT date_trunc('day', started_at) AS day, sum(credits_used) AS credits \
   FROM acquisition.source_run \
   WHERE started_at >= '2026-09-27T00:52:16Z' AND started_at < '2026-10-05T00:52:16Z' \
   GROUP BY 1 ORDER BY 1;"

# 4. Erros por tipo na janela (mesma tabela de telemetria do F20-19/F20-20)
docker compose -p opportunity-radar exec -T postgres psql -U postgres -d opportunity_radar -c \
  "SELECT model, error_kind, count(*) \
   FROM platform.ai_call_record \
   WHERE created_at >= '2026-09-27T00:52:16Z' AND created_at < '2026-10-05T00:52:16Z' \
   GROUP BY 1, 2 ORDER BY 3 DESC;"

# 5. scripts/doctor.py para o veredito operacional do dia final (breaker aberto,
#    saldo diário < 10%)
docker compose -p opportunity-radar run --rm api python scripts/doctor.py
```

Depois de rodar os cinco comandos, preencher a coluna "T7" da tabela da §3 com os
números reais, marcar "Veredicto" com meta batida / meta não batida / inconclusivo
(amostra ainda pequena mesmo em 7 dias é um resultado válido — não forçar um veredicto
binário se o volume real de operação na janela ficar baixo, como já ocorreu no T0), e
atualizar o `Status` no topo deste documento.

## 5. O que não foi feito nesta sessão (e por quê)

- **Nenhuma chamada real ao Groq.** A quota diária estava esgotada por outra sessão
  (baseline F20-21 já havia consumido ~170.000 dos tokens do dia); os números de custo
  de IA aqui vêm inteiramente da evidência já publicada do F20-21, não de uma nova
  medição.
- **Nenhum dado sintético.** Onde não há número real disponível (créditos Tavily,
  fallback/429 em produção), a célula diz "pendente" ou "sem dado", nunca um valor
  inventado ou extrapolado de outro contexto (o card proíbe isso explicitamente).
- **Nenhum teste novo.** O card lista "Testes: Nenhum teste novo" — este card entrega
  um documento, não código; não há comportamento de sistema para cobrir com teste.
- **Nenhum arquivo fora da lista "Arquivos" do card** foi alterado além do README e do
  estado-local (atualizações de status do roadmap, registradas no PR).


> **Reinício da janela de sete dias (2026-09-28).** O T0 anterior (`2026-09-27T00:52:16Z`) não valia: a stack real `opportunity-radar` ficou parada depois do reprocessamento `skills-v3` e o Docker Desktop esteve desligado, então não houve operação contínua. A stack real foi religada com o código atual e um novo T0 foi capturado em `2026-09-28T00:45:09Z` (`docs/44-roadmap-fase-20/evidencias/f20-janela-7d-t0-2026-09-28.json`: 20 fontes ativas, 648 oportunidades). A janela termina em `2026-10-05T00:45Z`; a stack precisa ficar ligada sem interrupção até lá.
