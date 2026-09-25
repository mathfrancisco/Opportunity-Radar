# CARD F20-09 — Tarefas (`AITask`) e roteamento por tarefa

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-07, F20-08
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §6

## Resultado

Cada tarefa tem uma cadeia de modelos e um orçamento configuráveis; trocar o modelo de uma tarefa é mudar configuração.

## Contexto

Hoje existe uma única análise com um modelo fixo. Este card cria o esqueleto do router; retry, breaker e quota entram em F20-10, F20-11 e F20-12 como pontos de extensão já previstos aqui.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/platform/ai/tasks.py` | `AITask`, `ModelRole`, `ModelRoute`, `TaskBudget`, `default_routes` |
| Criar | `src/opportunity_radar/platform/ai/router.py` | `AIRouter`, `RouterResult`, `Attempt` |
| Criar | `tests/backend/platform/ai/fakes.py` | `FakeProvider` reutilizável pelos próximos cards |
| Criar | `tests/backend/platform/ai/test_router.py` | testes |

## Interfaces

```python
# platform/ai/tasks.py
class AITask(StrEnum):
    JOB_MATCH = "job_match"
    JOB_CLASSIFICATION = "job_classification"
    JOB_EXTRACTION = "job_extraction"

class ModelRole(StrEnum):
    REASONING = "reasoning"
    FAST = "fast"
    ALT = "alt"

@dataclass(frozen=True)
class TaskBudget:
    max_input_tokens: int
    max_output_tokens: int
    reasoning_effort: str

@dataclass(frozen=True)
class ModelRoute:
    task: AITask
    chain: tuple[str, ...]      # nomes de modelo já resolvidos, em ordem
    budget: TaskBudget

def default_routes(settings: Settings) -> dict[AITask, ModelRoute]:
    """job_match: (reasoning, alt) 5000/900; job_classification: (fast, alt) 1500/300;
    job_extraction: (fast, reasoning) 3000/600; reasoning_effort = settings.ai_reasoning_effort."""

# platform/ai/router.py
@dataclass(frozen=True)
class Attempt:
    model: str
    attempt: int                # 0 = primeira tentativa naquele modelo
    error_kind: ErrorKind | None
    latency_ms: int | None

@dataclass(frozen=True)
class RouterResult:
    response: LLMResponse
    attempts: tuple[Attempt, ...]
    fallback_used: bool         # True se o modelo que respondeu não é chain[0]

class AIRouter:
    def __init__(self, provider: LLMProvider, routes: Mapping[AITask, ModelRoute], *,
                 fallback_enabled: bool = True) -> None: ...
    def route(self, task: AITask) -> ModelRoute: ...
    async def run(self, task: AITask, *, system: str, user: str, schema_name: str,
                  json_schema: Mapping[str, Any], temperature: float | None = None,
                  seed: int | None = None) -> RouterResult: ...
```

## Passos

1. Criar `tasks.py` com as interfaces e `default_routes` lendo `groq_*_model` e `ai_reasoning_effort`.
2. Criar `router.py`. Neste card, `run` tenta cada modelo da cadeia **uma vez**: sucesso devolve; `ProviderError` de kind `QUOTA`, `TRANSIENT` ou `INVALID_OUTPUT` passa para o próximo; `CONFIGURATION` e `REQUEST` relançam na hora.
3. Com `fallback_enabled=False`, a cadeia efetiva é só `chain[:1]`.
4. Se todos falharem, relançar o último `ProviderError`.
5. `max_completion_tokens` e `reasoning_effort` do `LLMRequest` vêm do `TaskBudget` da rota.
6. Criar `tests/backend/platform/ai/fakes.py` com `FakeProvider(script: dict[str, list[LLMResponse | ProviderError]])` que devolve respostas por modelo em ordem e registra as `LLMRequest` recebidas.
7. Escrever os testes.

## Não fazer

- Não implementar retry, breaker nem quota aqui (F20-10/11/12).
- Não colocar nome de modelo fixo fora de `Settings`.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Mudar `GROQ_REASONING_MODEL` muda o modelo chamado em `job_match`.
- [ ] `AI_FALLBACK_ENABLED=false` usa só o primeiro modelo.
- [ ] 401 no primeiro modelo não tenta o segundo.

## Testes

- `tests/backend/platform/ai/test_router.py`: `test_first_model_success`, `test_quota_moves_to_next_model`, `test_configuration_error_stops_chain`, `test_fallback_disabled_uses_first_only`, `test_all_fail_raises_last_error`, `test_budget_applied_to_request`, `test_unknown_task_raises_keyerror`.

## Comando de verificação

```bash
docker compose -p f20-09 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_router.py
docker compose -p f20-09 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-09 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
