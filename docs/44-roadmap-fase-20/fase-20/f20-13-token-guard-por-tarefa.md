# CARD F20-13 — Token Guard por tarefa

- **Status:** WIP — `platform/ai/budget.py` (`estimate_tokens`, `fits`) e `matching/text.py` (comentários/parâmetros apontando para `TaskBudget`) prontos, com `tests/backend/platform/ai/test_budget.py` e `tests/backend/matching/test_text.py` verdes (`docker compose ... run --rm api pytest -q`, `ruff check .`, `mypy`). Faltam os dois itens que dependem do adapter Groq (F20-17, fora do escopo dos Arquivos deste card): o `prepare` que chama `fits`/`overflow` antes do router, e a medição do erro de estimativa com 20+ vagas reais (`make eval-analysis`), que exige uma chamada real ao Groq — proibida nos testes deste card.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-09
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §7.2; [F16-05](../../38-roadmap-ia-e-busca/fase-16/f16-05-orcamento-de-tokens-e-limpador.md)

## Resultado

Todo prompt cabe no orçamento da sua tarefa antes de sair; o corte fica registrado; prompt impossível é recusado sem gastar quota.

## Contexto

O F16-05 já mede e corta (`matching/text.py`, e o `prepare` de `matching/ollama.py` com `_ratio_and_margin`, `estimate`, `prompt_budget`, `overflow`, `CONTEXT_OVERFLOW`). O orçamento era `num_ctx - num_predict`. Agora é `TaskBudget.max_input_tokens`. Tokens de raciocínio contam na saída, cobertos por `max_completion_tokens`. `AnalysisRequest.calibration` / `tokens_per_char` já trazem a calibração por modelo.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/platform/ai/budget.py` | `estimate_tokens`, `fits` |
| Alterar | `src/opportunity_radar/matching/text.py` | trocar referência a janela do Ollama por orçamento da tarefa (comentários e parâmetros) |
| Criar | `tests/backend/platform/ai/test_budget.py` | testes |

## Interfaces

```python
# platform/ai/budget.py
DEFAULT_CHARS_PER_TOKEN = 3.0
DEFAULT_MARGIN = 0.15   # 15 % acima da estimativa

def estimate_tokens(text: str, *, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
                    margin: float = DEFAULT_MARGIN) -> int:
    """ceil(len(text) / chars_per_token * (1 + margin))."""

def fits(system: str, user: str, budget: TaskBudget, **kw) -> bool: ...
```

## Passos

1. Criar `budget.py`.
2. No `prepare` do adapter Groq (F20-17), o orçamento passado ao limpador é `route.budget.max_input_tokens`; se nem a parte fixa cabe, `overflow=True` e o adapter devolve `AI_SKIPPED`/`CONTEXT_OVERFLOW` sem chamar o router.
3. A estimativa enviada ao Quota Guard é `estimate_tokens(system + user) + budget.max_output_tokens`.
4. Depois de cada resposta, registrar `prompt_tokens_estimate` e `prompt_tokens` reais em `AnalysisMetrics` (campos já existem) para calibração.
5. Medir com 20+ vagas reais (`make eval-analysis` ou `scripts/measure_descriptions.py`) o erro médio e máximo da estimativa e colar no PR.

## Não fazer

- Não reescrever o limpador do F16-05; só trocar o alvo do orçamento.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Nenhuma chamada sai com estimativa acima de `max_input_tokens` — garantido por `fits()`, provado em `test_fits_one_token_over_the_limit` e `test_fits_with_default_margin_rejects_a_prompt_the_raw_length_would_allow`.
- [ ] Prompt impossível: `CONTEXT_OVERFLOW` sem chamada ao provider e sem reserva de quota — depende do `prepare` do adapter Groq (F20-17), que ainda não existe; não marcado.
- [ ] Erro de estimativa medido e registrado no PR — exige medir com 20+ vagas reais via `make eval-analysis`/`scripts/measure_descriptions.py`, o que chamaria o Groq real; não feito nesta sessão (regra "não fazer chamada real ao Groq").

## Testes

- `tests/backend/platform/ai/test_budget.py`: `estimate_tokens` com margem, `fits` nos limites.
- `tests/backend/matching/test_text.py`: corte respeita o orçamento de tarefa.

## Comando de verificação

```bash
docker compose -p f20-13 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_budget.py tests/backend/matching/test_text.py
docker compose -p f20-13 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-13 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
