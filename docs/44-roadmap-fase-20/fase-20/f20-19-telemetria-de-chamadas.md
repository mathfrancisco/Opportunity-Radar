# CARD F20-19 — Telemetria de chamadas sem PII

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-17
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §8.5; [F16-13](../../38-roadmap-ia-e-busca/fase-16/f16-13-metricas-da-analise.md)

## Resultado

Cada chamada ao Groq deixa um registro sem PII que explica custo, falha e fallback.

## Contexto

A análise gravada (`matching/models.py`, `MatchAnalysisModel`, colunas de custo da migração `20260924_0018_analysis_cost.py`) guarda uma linha por análise, não por chamada. Com retry e fallback, uma análise pode ter várias chamadas.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `migrations/versions/20260926_0031_ai_call_record.py` | tabela `platform.ai_call_record` |
| Criar | `src/opportunity_radar/platform/ai/telemetry.py` | `AICallRecord`, `record_calls`, `purge_older_than` |
| Alterar | `src/opportunity_radar/matching/groq.py` | gravar `RouterResult.attempts` após cada `analyze` |
| Alterar | `src/opportunity_radar/worker.py` | purga diária no job de retenção existente |
| Alterar | `src/opportunity_radar/platform/config.py` | `ai_call_record_retention_days: int = 30` |
| Criar | `tests/backend/platform/ai/test_telemetry.py` | testes |

## Interfaces

```python
-- platform.ai_call_record
id              uuid primary key
created_at      timestamptz not null default now()
task            varchar(32)  not null
provider        varchar(32)  not null
model           varchar(128) not null
attempt         smallint     not null
success         boolean      not null
error_kind      varchar(32)  null
http_status     smallint     null
latency_ms      integer      null
prompt_tokens   integer      null
completion_tokens integer    null
fallback_used   boolean      not null
cache_hit       boolean      not null
prompt_version  varchar(32)  null
index (created_at), index (model, created_at)

@dataclass(frozen=True)
class AICallRecord:  # mesmos campos, sem id/created_at
    ...
```

## Passos

1. Migração `20260926_0031` com `down_revision = "20260926_0030"` (confirmar com `alembic heads`).
2. Adicionar `http_status` e `latency_ms` a `Attempt` do router (F20-09) se ainda não houver.
3. `record_calls(engine, records)` insere em lote, chamado com `asyncio.to_thread` no adapter.
4. Reuso por cache (F20-16) grava um registro com `cache_hit=True`, `attempt=0`, `success=True`, sem tokens.
5. `purge_older_than(engine, days)` apaga em lotes; plugar no job de retenção do `worker.py`.
6. Escrever os testes.

## Não fazer

- Nunca gravar prompt, resposta, payload, chave nem dado de perfil.
- Não criar coluna de texto livre além de `error_kind`.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Uma análise com um retry e um fallback gera 3 registros coerentes.
- [ ] Teste confirma que nenhuma coluna contém valores do payload de teste.
- [ ] Purga remove só registros mais antigos que o limite.

## Testes

- `tests/backend/platform/ai/test_telemetry.py`: montagem de registros a partir de `RouterResult`, ausência de PII, purga (integração).

## Comando de verificação

```bash
docker compose -p f20-19 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_telemetry.py
docker compose -p f20-19 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-19 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Critérios marcados; comando de verificação passa também com `RUN_DATABASE_INTEGRATION=1`; CI verde.
