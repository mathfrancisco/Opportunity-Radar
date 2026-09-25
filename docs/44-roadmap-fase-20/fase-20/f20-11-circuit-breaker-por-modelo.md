# CARD F20-11 — Circuit breaker por modelo

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-10
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §7.4

## Resultado

Um modelo que falha seguidamente é pulado por um tempo sem gastar tentativa e volta a ser testado sozinho.

## Contexto

Só falhas `TRANSIENT` contam. 429 é assunto do Quota Guard e do `blocked_until` do F20-10.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/platform/ai/breaker.py` | `CircuitBreaker`, `BreakerState` |
| Alterar | `src/opportunity_radar/platform/ai/router.py` | consultar e alimentar o breaker |
| Criar | `tests/backend/platform/ai/test_breaker.py` | testes |

## Interfaces

```python
class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(self, *, failures: int = 5, cooldown_seconds: float = 120,
                 clock: Callable[[], float] = time.monotonic) -> None: ...
    def allow(self, model: str) -> bool: ...          # OPEN e cooldown não passou -> False
    def record_success(self, model: str) -> None: ...  # -> CLOSED, zera contador
    def record_failure(self, model: str) -> None: ...  # conta; atingiu `failures` -> OPEN
    def state(self, model: str) -> BreakerState: ...
    def snapshot(self) -> dict[str, BreakerState]: ...
```

## Passos

1. Implementar `CircuitBreaker` em memória (dict por modelo).
2. Após o cooldown, `allow` devolve `True` uma vez e o estado vira `HALF_OPEN`; sucesso fecha, falha reabre com novo cooldown.
3. No router: antes de chamar um modelo, `if not breaker.allow(model): pular`; em `TRANSIENT` chamar `record_failure` (uma vez por tentativa); em sucesso `record_success`.
4. `AIRouter.__init__` recebe `breaker: CircuitBreaker | None = None` (cria um padrão se `None`).
5. Escrever os testes com relógio controlado.

## Não fazer

- Não contar `QUOTA`, `CONFIGURATION`, `REQUEST` nem `INVALID_OUTPUT` como falha do breaker.
- Não persistir o estado no banco.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] 5 falhas transitórias abrem; o router pula o modelo aberto.
- [ ] Depois de 120 s, uma chamada de prova; sucesso fecha.

## Testes

- `tests/backend/platform/ai/test_breaker.py`: `test_opens_after_n_failures`, `test_half_open_after_cooldown`, `test_success_closes`, `test_failure_in_half_open_reopens`, `test_quota_does_not_count`.
- `tests/backend/platform/ai/test_router.py`: `test_router_skips_open_model`.

## Comando de verificação

```bash
docker compose -p f20-11 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_breaker.py tests/backend/platform/ai/test_router.py
docker compose -p f20-11 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-11 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
