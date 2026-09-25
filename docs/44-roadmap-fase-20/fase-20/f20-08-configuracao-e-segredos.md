# CARD F20-08 — Configuração da IA cloud e segredos

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-07
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §5

## Resultado

O operador liga a IA com `AI_ENABLED=true` e `GROQ_API_KEY` no `.env`; sem chave, a análise é bloqueada por configuração e o radar segue normal.

## Contexto

`platform/config.py` usa `pydantic_settings.BaseSettings` com `env_file=".env"`. `matching/adapters.py:15` (`build_analysis_adapter`) decide entre adapter real e `NullAnalysisAdapter`. `.env` já está no `.gitignore` (linha 2).

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/platform/ai/config.py` | `AISettings`, `ai_status` |
| Alterar | `src/opportunity_radar/platform/config.py` | campos `ai_*` e `groq_*` |
| Alterar | `src/opportunity_radar/matching/adapters.py` | escolha Groq/Null com motivo |
| Alterar | `src/opportunity_radar/matching/analysis.py` | `AnalysisFailureCode.NOT_CONFIGURED` e `QUOTA_EXHAUSTED` |
| Alterar | `.env.example` | variáveis da SPEC §5 |
| Criar | `tests/backend/platform/ai/test_config.py` | testes |

## Interfaces

```python
# platform/config.py — campos novos em Settings (nomes = variáveis de ambiente)
ai_enabled: bool = False
ai_provider: str = "groq"
groq_api_key: SecretStr = SecretStr("")
groq_base_url: str = "https://api.groq.com/openai/v1"
groq_reasoning_model: str = "openai/gpt-oss-120b"
groq_fast_model: str = "openai/gpt-oss-20b"
groq_alt_model: str = "qwen/qwen3.8-27b"
ai_timeout_seconds: float = 25.0
ai_connect_timeout_seconds: float = 5.0
ai_max_retries: int = 2
ai_fallback_enabled: bool = True
ai_reasoning_effort: str = "low"
ai_analysis_prompt: str = "v1"
ai_daily_requests_soft_limit: int = 850
ai_daily_tokens_soft_limit: int = 170_000
ai_minute_tokens_soft_limit: int = 7_000
ai_minute_requests_soft_limit: int = 25
ai_breaker_failures: int = 5
ai_breaker_cooldown_seconds: int = 120

# platform/ai/config.py
class AIState(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"                    # AI_ENABLED=false
    BLOCKED_BY_CONFIGURATION = "blocked_by_configuration"  # ligada, sem chave

def ai_status(settings: Settings) -> AIState: ...

# matching/analysis.py — novos códigos
class AnalysisFailureCode(StrEnum):
    ...
    NOT_CONFIGURED = "NOT_CONFIGURED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
```

## Passos

1. Adicionar os campos acima em `Settings`; `groq_api_key` é `SecretStr`.
2. Validar no start: `ai_provider == "groq"`; `ai_reasoning_effort` em {`low`,`medium`,`high`}; limites positivos. Erro de validação derruba o start com mensagem clara.
3. Criar `ai_status`.
4. Adicionar `NOT_CONFIGURED` e `QUOTA_EXHAUSTED` em `AnalysisFailureCode`.
5. Em `build_analysis_adapter`: `DISABLED` → `NullAnalysisAdapter()`; `BLOCKED_BY_CONFIGURATION` → `NullAnalysisAdapter()` e log `warning` único "groq api key missing"; `ENABLED` → `GroqAnalysisAdapter` (até o F20-17 existir, manter o adapter atual).
6. Atualizar `.env.example` com todas as variáveis e `GROQ_API_KEY=` vazio.
7. Escrever os testes.

## Não fazer

- Não ler o `.env` real nos testes; usar `Settings(_env_file=None, ...)` ou `monkeypatch.setenv`.
- Não usar `str(settings.groq_api_key)`; usar `.get_secret_value()` só dentro do provider.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Sem chave: `ai_status` = `blocked_by_configuration` e nenhuma exceção.
- [ ] `AI_REASONING_EFFORT=extreme` falha no start.
- [ ] `.env.example` lista todas as variáveis novas.

## Testes

- `tests/backend/platform/ai/test_config.py`: padrões, validação de `reasoning_effort`, `ai_status` nos três estados, `repr(settings)` sem a chave.
- `tests/backend/matching/test_adapters.py` (criar): `build_analysis_adapter` nos três estados.

## Comando de verificação

```bash
docker compose -p f20-08 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_config.py tests/backend/matching/test_adapters.py
docker compose -p f20-08 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-08 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
