# CARD F20-13 — Token Guard por tarefa

- **Status:** Feito — `platform/ai/budget.py` (`estimate_tokens`, `fits`) e `matching/text.py` prontos desde a sessão anterior; `GroqAnalysisAdapter.prepare` (F20-17) agora chama `fits()` como portão de overflow antes do router, e o erro de estimativa foi medido com uma chamada real ao Groq (autorizada pelo usuário, fora de CI) via `scripts/measure_token_estimate_error.py`. Números na seção "Medição real" abaixo.
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
- [x] Prompt impossível: `CONTEXT_OVERFLOW` sem chamada ao provider e sem reserva de quota — `GroqAnalysisAdapter.prepare` (F20-17) chama `platform.ai.budget.fits(system, user_content, route.budget)` e marca `overflow=True` sem tocar o router; `matching.groq.analyze` devolve `AI_FAILED`/`CONTEXT_OVERFLOW` antes de qualquer chamada. Provado em `tests/backend/matching/test_groq_adapter.py::test_overflow_skipped_without_call` (perfil gigante, `provider.requests == []`).
- [x] Erro de estimativa medido e registrado no PR — medido com uma chamada real ao Groq autorizada pelo usuário, fora de CI, via `scripts/measure_token_estimate_error.py --limit 25` (banco de dev vazio; postings reais e públicos de boards Greenhouse usados como fallback, exatamente como o card previa). Números abaixo.

## Testes

- `tests/backend/platform/ai/test_budget.py`: `estimate_tokens` com margem, `fits` nos limites.
- `tests/backend/matching/test_text.py`: corte respeita o orçamento de tarefa.

## Medição real (fora de CI)

`scripts/measure_token_estimate_error.py` (não é pytest; nunca roda em CI) chama o Groq
real com `GROQ_API_KEY` do usuário, via `docker compose run --rm -e GROQ_API_KEY api ...`,
comparando `platform.ai.budget.estimate_tokens(system + user)` com o `usage.prompt_tokens`
real de cada resposta. O banco de desenvolvimento estava vazio (0 postings), então o
script caiu no plano B do próprio card: vagas reais e públicas de boards do Greenhouse
(`gitlab`, `elastic`, `airbnb`, `stripe`, `asana`), com o texto completo da descrição
embutido no snapshot para variar o tamanho do prompt de forma realista. Modelo:
`openai/gpt-oss-120b` (o mesmo da rota `JOB_MATCH`).

Resultado (25 vagas reais, `openai/gpt-oss-120b`, `estimate_tokens` com os padrões de
`platform.ai.budget`, `chars_per_token=3.0`, `margin=0.15`):

| Medida | Valor |
| --- | --- |
| Vagas medidas | 25 |
| Erro médio `(actual - estimate) / actual` | -67.7 % |
| Erro mediano | -67.0 % |
| Maior \|erro\| | -75.0 % |
| Subestimativas (`actual > estimate`) | 0 de 25 |
| Pior subestimativa | nenhuma |

O erro é sempre negativo: em nenhuma das 25 chamadas reais o `usage.prompt_tokens` real
superou a estimativa (`estimate_tokens`) — a direção seguramente conservadora que o
docstring de `platform/ai/budget.py` pede ("overestimating only rejects a prompt sooner,
underestimating would send one that overflows without anyone knowing"). O custo é que a
constante `DEFAULT_CHARS_PER_TOKEN = 3.0` reserva no Quota Guard cerca de 3x mais tokens
do que o gpt-oss-120b realmente consome nesse texto em inglês (chars/token real ≈ 4.3-4.6
nessas 25 amostras); isso nunca gera `CONTEXT_OVERFLOW` indevido dentro do orçamento de
5000 tokens da rota `JOB_MATCH` (a margem é grande), mas reserva mais quota do que o
necessário por chamada. Ajustar a constante fica fora do escopo deste card — o critério
de aceite pede a medição e o registro, não a recalibração.

## Comando de verificação

```bash
docker compose -p f20-13 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_budget.py tests/backend/matching/test_text.py
docker compose -p f20-13 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-13 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
