# CARD F20-12 — Quota Guard persistente por modelo

- **Status:** Feito — `tests/backend/platform/ai/test_quota.py` e `tests/backend/test_ai_quota_integration.py` com `RUN_DATABASE_INTEGRATION=1` (`docker compose ... run --rm api pytest -q`, `ruff check .` e `mypy` verdes); `alembic upgrade head` / `downgrade base` / `upgrade head` verificados manualmente na mesma sessão de Docker.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-10
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §4.1, §7.1

## Resultado

O radar nunca estoura a quota do Free Plan sem saber: reserva antes, ajusta pelo uso real, pula modelo sem saldo e diz quando a análise volta.

## Contexto

API e worker podem chamar o Groq ao mesmo tempo, e o worker pode reiniciar. O banco tem o schema `platform` (migração `20260910_0001`). A última migração é `20260925_0029` (`migrations/versions/20260925_0029_allowed_countries.py`); seguir o mesmo formato (docstring, `revision`, `down_revision`, `SCHEMA`). O acesso ao banco no worker é síncrono (`Engine`); o adapter é `async`, então o guard é síncrono e chamado com `asyncio.to_thread`.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `migrations/versions/20260926_0030_ai_quota_usage.py` | tabela `platform.ai_quota_usage` |
| Criar | `src/opportunity_radar/platform/ai/quota.py` | `QuotaLimits`, `QuotaGuard`, `Reservation` |
| Alterar | `src/opportunity_radar/platform/ai/router.py` | reservar antes de cada chamada, ajustar depois |
| Criar | `tests/backend/platform/ai/test_quota.py` | unitário |
| Criar | `tests/backend/test_ai_quota_integration.py` | integração com Postgres |

## Interfaces

```python
-- platform.ai_quota_usage
model          varchar(128) not null
window_kind    varchar(8)   not null   -- 'minute' | 'day'
window_start   timestamptz  not null   -- truncado ao minuto / ao dia UTC
requests       integer      not null default 0
tokens         integer      not null default 0
remaining_requests_reported integer null   -- último x-ratelimit-remaining-requests
remaining_tokens_reported   integer null
updated_at     timestamptz  not null default now()
primary key (model, window_kind, window_start)

# platform/ai/quota.py
@dataclass(frozen=True)
class QuotaLimits:
    minute_requests: int
    minute_tokens: int
    day_requests: int
    day_tokens: int

@dataclass(frozen=True)
class Reservation:
    model: str
    minute_start: datetime
    day_start: datetime
    tokens: int

class QuotaGuard:
    def __init__(self, engine: Engine, limits: QuotaLimits,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None: ...
    def reserve(self, model: str, estimated_tokens: int) -> Reservation | None:
        """None = sem saldo. Atômico: INSERT ... ON CONFLICT DO UPDATE ... WHERE
        requests + 1 <= limite AND tokens + estimado <= limite RETURNING ..."""
    def settle(self, reservation: Reservation, actual_tokens: int | None,
               rate_limit: RateLimit | None) -> None: ...
    def release(self, reservation: Reservation) -> None: ...   # falha sem consumo
    def next_available_at(self, model: str) -> datetime: ...
    def snapshot(self) -> list[dict[str, Any]]: ...            # para métricas (F20-20)
```

## Passos

1. Criar a migração com `revision = "20260926_0030"` e `down_revision` = saída de `alembic heads` no momento (hoje `"20260925_0029"`). `downgrade` apaga a tabela.
2. Implementar `reserve` com um único `INSERT ... ON CONFLICT (model, window_kind, window_start) DO UPDATE ... WHERE ... RETURNING` para a janela `minute` e outro para `day`, dentro de uma transação; se o segundo falhar, a transação desfaz o primeiro.
3. Limite efetivo de requisições = `min(limite interno, remaining_requests_reported + requests já contadas)` quando houver valor reportado; o mesmo para tokens.
4. `settle`: ajustar `tokens` pela diferença `actual_tokens - reservation.tokens` (se `actual_tokens` não `None`) e gravar os `remaining_*_reported`.
5. `release`: devolver 1 requisição e os tokens reservados (usado quando o erro é `CONFIGURATION`, `REQUEST` ou conexão recusada antes do envio).
6. No router: antes de cada chamada `reservation = await asyncio.to_thread(guard.reserve, model, estimated)`; `None` → tratar como `blocked_until` até `next_available_at`; depois `settle` ou `release`.
7. `AIRouter.run` ganha o parâmetro `estimated_input_tokens: int` (vem do Token Guard, F20-13; até lá, usar `len(system + user) // 3`).
8. `QuotaLimits` vem de `Settings`: `ai_minute_requests_soft_limit`, `ai_minute_tokens_soft_limit`, `ai_daily_requests_soft_limit`, `ai_daily_tokens_soft_limit`.
9. Escrever testes unitários (engine SQLite não serve: usar o teste de integração para a atomicidade) e o de integração.

## Não fazer

- Não guardar contador só em memória.
- Não bloquear o event loop: chamar o guard via `asyncio.to_thread`.
- Não apagar linhas antigas aqui; retenção fica para o F20-19.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Duas reservas concorrentes (20 threads, limite 10) resultam em exatamente 10 reservas (`test_concurrent_reservations_never_exceed_the_limit`).
- [x] Reiniciar o processo não zera o consumo do dia (`test_restart_does_not_reset_the_days_consumption`).
- [x] Virada do minuto libera reserva de minuto; virada do dia UTC libera a do dia (`test_minute_rollover_frees_the_minute_reservation_but_not_the_day`, `test_day_rollover_frees_the_day_reservation`).
- [x] `alembic upgrade head` e `alembic downgrade base` passam (verificado manualmente: `upgrade head` → `downgrade -1` → `upgrade head` → `downgrade base` → `upgrade head`, sem erro).

## Testes

- `tests/backend/platform/ai/test_quota.py`: cálculo de janela, limite efetivo com valor reportado, `release`.
- `tests/backend/test_ai_quota_integration.py` (marcado como os outros `*_integration.py`): concorrência, persistência, virada de janela.

## Comando de verificação

```bash
docker compose -p f20-12 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_quota.py tests/backend/test_ai_quota_integration.py
docker compose -p f20-12 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-12 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Critérios marcados; comando de verificação passa também com `RUN_DATABASE_INTEGRATION=1`; CI verde.
