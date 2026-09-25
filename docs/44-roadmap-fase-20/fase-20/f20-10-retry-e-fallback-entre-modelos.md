# CARD F20-10 — Retry com jitter e fallback entre modelos

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-09
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §7.3

## Resultado

Falha transitória é tentada de novo no mesmo modelo; 429 e saída inválida passam ao próximo modelo; erro de configuração nunca gera retry; o número de chamadas tem teto provado.

## Contexto

O adapter antigo fazia retry com `retry_after_seconds * 2**attempt * (1 + jitter/4)` (`matching/ollama.py`, `_analyze_with_retries`). O router do F20-09 já passa ao próximo modelo; falta o retry no mesmo modelo e o reparo de saída inválida.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/platform/ai/router.py` | retry, backoff, reparo, `retry_after` por modelo |
| Alterar | `tests/backend/platform/ai/test_router.py` | testes novos |

## Interfaces

```python
class AIRouter:
    def __init__(self, provider, routes, *, fallback_enabled: bool = True,
                 max_retries: int = 2,
                 sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 jitter: Callable[[], float] = random.random,
                 clock: Callable[[], float] = time.monotonic,
                 validator: Callable[[str], None] | None = None) -> None: ...
    # validator: levanta ProviderError(INVALID_OUTPUT) se o texto não passa no schema (F20-14 injeta)
```

## Passos

1. `TRANSIENT`: repetir no mesmo modelo até `max_retries` vezes; espera antes da tentativa `n` (1-based) = `2 ** (n - 1)` segundos × `(1 + jitter() / 4)`, via `sleeper`.
2. `QUOTA`: não repetir; guardar `blocked_until[model] = clock() + (retry_after_seconds or 60)`; próximo modelo. Em chamadas futuras, pular modelo com `blocked_until` no futuro.
3. `INVALID_OUTPUT` (vindo do provider ou do `validator`): uma única nova chamada no mesmo modelo, com a mensagem `user` acrescida de `\n\nA resposta anterior foi rejeitada: <summary>. Responda só com JSON válido no schema.`; se falhar de novo, próximo modelo.
4. `CONFIGURATION` e `REQUEST`: relançar na hora.
5. Registrar cada tentativa em `RouterResult.attempts`.
6. Todas as tentativas esgotadas: relançar o último `ProviderError`; se todos os modelos foram pulados por `blocked_until`, lançar `ProviderError(QUOTA, "all models rate limited", retry_after_seconds=<menor espera>)`.
7. Escrever os testes com `sleeper` que só registra as esperas e `clock` controlado.

## Não fazer

- Não usar `time.sleep`.
- Não repetir 429 no mesmo modelo.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Número máximo de chamadas por `run` = `len(chain) × (1 + max_retries)`, provado em teste com todos transitórios.
- [ ] Esperas registradas: `[1×j, 2×j]` para `max_retries=2`.
- [ ] 401 → uma chamada só.

## Testes

- `tests/backend/platform/ai/test_router.py`: `test_transient_retried_then_success`, `test_backoff_sequence_with_jitter`, `test_call_ceiling`, `test_429_not_retried_same_model`, `test_blocked_model_skipped_until_retry_after`, `test_invalid_output_repaired_once`, `test_invalid_output_twice_moves_on`, `test_all_models_blocked_raises_quota`.

## Comando de verificação

```bash
docker compose -p f20-10 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_router.py
docker compose -p f20-10 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-10 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
