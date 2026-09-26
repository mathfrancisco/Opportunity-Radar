# CARD F20-20 — Métricas da IA na API, no Overview e no `doctor`

- **Status:** Feito — `src/opportunity_radar/platform/ai/metrics.py` (`ai_metrics`), bloco `ai` em `GET /analysis-metrics` (`presentation/http/dashboard.py`), card "IA (Groq)" em `apps/web/src/routes/OverviewPage.tsx`, `check_ai` em `scripts/doctor.py`; testes `tests/backend/platform/ai/test_metrics.py` (4), `tests/backend/dashboard/test_analysis_metrics.py` (+1), `tests/backend/test_doctor.py` (+2) — 20 passed com `RUN_DATABASE_INTEGRATION=1`; `ruff check .` e `mypy` limpos; `npm run check` (lint+typecheck+vitest 125 passed+build) dentro do estágio `build` do Dockerfile do frontend.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-19, F20-11, F20-12
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §8.5; [F16-13](../../38-roadmap-ia-e-busca/fase-16/f16-13-metricas-da-analise.md)

## Resultado

O operador vê quanto de quota foi gasto, quanto falta no dia, a taxa de fallback e de 429 e se algum breaker está aberto.

## Contexto

O F16-13 expõe métricas da análise em `presentation/http/dashboard.py` (linha ~405 usa `current_model`), testadas em `tests/backend/dashboard/test_analysis_metrics.py`; o card aparece em `apps/web/src/routes/OverviewPage.tsx`; o `doctor` tem seção própria.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/platform/ai/metrics.py` | `ai_metrics(engine, guard, breaker, since)` |
| Alterar | `src/opportunity_radar/presentation/http/dashboard.py` | incluir bloco `ai` na resposta de métricas |
| Alterar | `apps/web/src/routes/OverviewPage.tsx` | card "IA (Groq)" |
| Alterar | `scripts/doctor.py` | `check_ai` mostra saldo e breaker |
| Criar | `tests/backend/platform/ai/test_metrics.py` | agregação |
| Alterar | `tests/backend/dashboard/test_analysis_metrics.py` | bloco `ai` |

## Interfaces

```python
# resposta (bloco novo dentro das métricas do dashboard)
"ai": {
  "state": "enabled" | "disabled" | "blocked_by_configuration",
  "window_hours": 24,
  "by_model": [
    {"model": "openai/gpt-oss-120b", "requests": 120, "success_rate": 0.97,
     "rate_limited_rate": 0.02, "fallback_rate": 0.01, "latency_ms_avg": 900,
     "latency_ms_p95": 2100, "prompt_tokens": 250000, "completion_tokens": 50000,
     "json_valid_rate": 0.99, "breaker": "closed",
     "day_requests_used": 120, "day_requests_limit": 850,
     "day_tokens_used": 300000, "day_tokens_limit": 170000}
  ],
  "cache_hit_rate": 0.35
}
```

## Passos

1. Implementar `ai_metrics` com SQL agregando `platform.ai_call_record` nas últimas 24 h e lendo `QuotaGuard.snapshot()` e `CircuitBreaker.snapshot()`.
2. p95 via `percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)`.
3. `json_valid_rate` = 1 − (registros com `error_kind = 'invalid_output'` / total).
4. Incluir o bloco no endpoint de métricas existente sem mudar os campos antigos.
5. No Overview, um card com saldo diário (barra usado/limite) por modelo, taxa de fallback e breaker aberto em destaque.
6. No `doctor`, breaker aberto ou saldo diário < 10 % vira alerta.

## Não fazer

- Não remover campos existentes da resposta de métricas (o frontend atual depende deles).
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Overview mostra saldo diário e taxa de fallback por modelo.
- [x] `doctor` alerta breaker aberto e saldo < 10 % (heurística de F20-19: `_models_with_a_recent_failure_streak`, já que o breaker em memória não é visível a partir do processo do `doctor` — ver observações no PR).
- [x] `cd apps/web && npm run check` passa.

## Testes

- `tests/backend/platform/ai/test_metrics.py`: agregação com registros sintéticos (sucesso, 429, fallback, inválido).
- `tests/backend/dashboard/test_analysis_metrics.py`: bloco `ai` presente.
- `tests/backend/test_doctor.py`: alertas.

## Comando de verificação

```bash
docker compose -p f20-20 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_metrics.py tests/backend/dashboard/test_analysis_metrics.py tests/backend/test_doctor.py
docker compose -p f20-20 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-20 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
