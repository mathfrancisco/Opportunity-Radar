# CARD F20-06 — Health, doctor, scripts e testes sem Ollama

- **Status:** Quase feito — `platform/health.py` tem `ai_health` (sem chamada de rede) no lugar de `ollama_health`; `/health` devolve `ai`; `scripts/doctor.py` tem `check_ai` (nunca imprime a chave, testado); `scripts/eval_analysis.py` usa `build_analysis_adapter`; `scripts/measure_descriptions.py` usa o `TaskBudget` de `job_match`; `tests/e2e/fake_ollama.py` apagado; frontend (`health/api.ts`, `AnalysisPanel.tsx`, `OverviewPage.tsx`) e seus testes atualizados; `npm run check` passa. Ressalva: `grep -rni ollama` ainda acha uma linha de comentário histórico em `matching/groq.py` ("the retired `OllamaAnalysisAdapter`") — fora de escopo por instrução explícita de não tocar `matching/groq.py` além de limpeza de import; ver nota no PR.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-04, F20-05, F20-08
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §2.2

## Resultado

`grep -rni ollama src scripts tests compose*.yaml Makefile` volta vazio; health, `doctor` e scripts falam de "IA (Groq)".

## Contexto

Restos após F20-04 e F20-05: `platform/health.py` (`ollama_health`, linhas 47-60); `presentation/http/routes.py` linhas 4, 41, 47 (campo `ollama` no `/health`); `presentation/http/dashboard.py` linha 405 (`current_model=settings.ollama_model_analysis`); `scripts/doctor.py` `check_ollama` (linhas 357-380); `scripts/eval_analysis.py` (constrói `OllamaAnalysisAdapter`, linhas 49-73); `scripts/measure_descriptions.py` linha 117 (`num_ctx`); `scripts/export_prompt_schema.py` (comentário); comentários em `matching/analysis.py:4`, `matching/evaluation.py:13`, `matching/models.py:231`, `matching/text.py:7`, `matching/context.py:3`; `tests/e2e/fake_ollama.py`; `tests/backend/test_health.py`; `tests/backend/dashboard/test_analysis_metrics.py`; `tests/backend/matching/test_analysis_persistence.py` e `test_analysis_queue.py`; frontend `apps/web/src/features/health/api.ts` linhas 41-44, `AnalysisPanel.tsx` linha 144, `OverviewPage.tsx` linha 540.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/platform/health.py` | trocar `ollama_health` por `ai_health` (usa `ai_status` do F20-08) |
| Alterar | `src/opportunity_radar/presentation/http/routes.py` | `/health` devolve a chave `ai` no lugar de `ollama` |
| Alterar | `src/opportunity_radar/presentation/http/dashboard.py` | `current_model` passa a vir de `AISettings` (modelo `reasoning`) |
| Alterar | `scripts/doctor.py` | `check_ollama` → `check_ai` (ligada/bloqueada, chave presente sim/não, modelos) |
| Alterar | `scripts/eval_analysis.py` | construir o adapter por `build_analysis_adapter(settings)`; remover opções `--num-ctx`/`--num-predict` |
| Alterar | `scripts/measure_descriptions.py` | usar o orçamento do `TaskBudget` de `job_match` no lugar de `num_ctx` |
| Alterar | `comentários em `matching/*.py` e `scripts/export_prompt_schema.py`` | trocar "Ollama" por "provedor"/"Groq" |
| Apagar | `tests/e2e/fake_ollama.py` | substituído por `fake_groq.py` |
| Alterar | `tests/backend/test_health.py, tests/backend/test_doctor.py, tests/backend/dashboard/test_analysis_metrics.py, tests/backend/matching/test_analysis_persistence.py, tests/backend/matching/test_analysis_queue.py` | remover referências ao Ollama |
| Alterar | `apps/web/src/features/health/api.ts (+ `api.test.ts`)` | ler `health.ai`; mensagem "IA indisponível. A coleta e as regras continuam disponíveis." |
| Alterar | `apps/web/src/features/matching/AnalysisPanel.tsx` | botão "Analisar com IA" |
| Alterar | `apps/web/src/routes/OverviewPage.tsx` | hint "IA (Groq) indisponível, sem quota ou desligada" |

## Interfaces

```python
# platform/health.py
def ai_health(settings: Settings) -> DependencyHealth:
    """Nunca faz chamada de rede. healthy = IA ligada e chave presente;
    degraded = desligada ou sem chave (detalhe: "ai disabled" | "groq api key missing")."""
```

## Passos

1. Criar `ai_health` em `platform/health.py` sem chamada de rede e apagar `ollama_health`.
2. Em `routes.py`, trocar a chave `"ollama"` por `"ai"` no JSON do `/health`.
3. No frontend, ler `health.ai` em `features/health/api.ts`, atualizar `api.test.ts` e os textos de `AnalysisPanel.tsx` e `OverviewPage.tsx`.
4. Em `scripts/doctor.py`, reescrever `check_ollama` como `check_ai`, mostrando: IA ligada/desligada, chave presente (sim/não), modelo por papel. Nunca imprimir a chave.
5. Em `scripts/eval_analysis.py`, trocar a construção manual do adapter por `build_analysis_adapter(settings)`.
6. Em `scripts/measure_descriptions.py`, trocar `num_ctx`/`num_predict` pelo `TaskBudget` de `job_match`.
7. Atualizar comentários que citam Ollama.
8. Apagar `tests/e2e/fake_ollama.py`; ajustar os testes listados.
9. Rodar `grep -rni ollama src scripts tests compose*.yaml Makefile apps/web/src` e zerar.

## Não fazer

- Não fazer chamada ao Groq no health (custaria quota a cada checagem).
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] `grep -rni ollama src scripts tests compose*.yaml Makefile apps/web/src` não retorna nada — falta 1 linha em `matching/groq.py` (comentário histórico), fora de escopo por instrução explícita de não tocar esse arquivo além de limpeza de import.
- [x] `/health` tem a chave `ai` e não tem `ollama`.
- [x] `npm run check` em `apps/web` passa.

## Testes

- `tests/backend/test_health.py`: `ai_health` nos estados ligada, desligada, sem chave.
- `tests/backend/test_doctor.py`: `check_ai` nunca imprime a chave.
- `apps/web/src/features/health/api.test.ts`: leitura de `health.ai`.

## Comando de verificação

```bash
docker compose -p f20-06 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/test_health.py tests/backend/test_doctor.py tests/backend/dashboard tests/backend/matching
docker compose -p f20-06 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-06 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Critérios marcados, comando de verificação e `cd apps/web && npm run check` passam, CI verde.
