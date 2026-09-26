# CARD F20-07 — Porta `LLMProvider` e `GroqProvider`

- **Status:** Feito
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §3.1, §4.2, §7.3

## Resultado

Existe um cliente Groq testável, atrás de uma porta neutra, que envia chat completion com JSON Schema estrito e devolve conteúdo, uso, cabeçalhos de quota e erro classificado.

## Contexto

O projeto usa `httpx` direto em todos os clientes (ver o construtor de `OllamaAnalysisAdapter` em `matching/ollama.py:97-160` como referência de timeouts, `client_factory`, `sleeper` e `jitter` injetáveis). Não existe pasta `platform/ai/` nem `tests/backend/platform/`. O contrato da API está na SPEC 43 §4.2.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/platform/ai/__init__.py` | vazio |
| Criar | `src/opportunity_radar/platform/ai/errors.py` | `ErrorKind`, `ProviderError` |
| Criar | `src/opportunity_radar/platform/ai/providers/__init__.py` | vazio |
| Criar | `src/opportunity_radar/platform/ai/providers/base.py` | `LLMProvider`, `LLMRequest`, `LLMResponse`, `Usage`, `RateLimit` |
| Criar | `src/opportunity_radar/platform/ai/providers/groq.py` | `GroqProvider`, `parse_duration` |
| Criar | `tests/backend/platform/__init__.py e tests/backend/platform/ai/__init__.py` | vazios |
| Criar | `tests/backend/platform/ai/test_groq_provider.py` | testes |

## Interfaces

```python
# platform/ai/errors.py
class ErrorKind(StrEnum):
    TRANSIENT = "transient"          # timeout, conexão, 5xx
    QUOTA = "quota"                  # 429
    INVALID_OUTPUT = "invalid_output"  # corpo sem JSON válido ou fora do schema
    CONFIGURATION = "configuration"  # 401, 403, 404
    REQUEST = "request"              # 400, 413, 422

class ProviderError(Exception):
    def __init__(self, kind: ErrorKind, summary: str, *, status: int | None = None,
                 retry_after_seconds: float | None = None, model: str | None = None) -> None: ...

# platform/ai/providers/base.py
@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None
    completion_tokens: int | None
    prompt_ms: int | None       # usage.prompt_time * 1000
    completion_ms: int | None   # usage.completion_time * 1000

@dataclass(frozen=True)
class RateLimit:
    limit_requests: int | None
    limit_tokens: int | None
    remaining_requests: int | None
    remaining_tokens: int | None
    reset_requests_seconds: float | None
    reset_tokens_seconds: float | None

@dataclass(frozen=True)
class LLMRequest:
    model: str
    system: str
    user: str
    schema_name: str
    json_schema: Mapping[str, Any]
    strict: bool = True
    max_completion_tokens: int = 900
    temperature: float | None = None
    seed: int | None = None
    reasoning_effort: str | None = None

@dataclass(frozen=True)
class LLMResponse:
    model: str
    content: str
    usage: Usage
    rate_limit: RateLimit
    latency_ms: int
    finish_reason: str | None

class LLMProvider(Protocol):
    name: str
    async def complete(self, request: LLMRequest) -> LLMResponse: ...

# platform/ai/providers/groq.py
def parse_duration(value: str | None) -> float | None:
    """'2m59.56s' -> 179.56; '7.66s' -> 7.66; '120ms' -> 0.12; inválido/None -> None."""

class GroqProvider:
    name = "groq"
    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: float = 25.0,
                 connect_timeout_seconds: float = 5.0,
                 client_factory: Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None: ...
    def __repr__(self) -> str:  # nunca inclui a chave
        return f"GroqProvider(base_url={self._base_url!r})"
    async def complete(self, request: LLMRequest) -> LLMResponse: ...
```

## Passos

1. Criar `errors.py` e `providers/base.py` exatamente com as interfaces acima.
2. Em `groq.py`, montar o corpo: `model`, `messages` (system + user), `response_format` com `type: json_schema` e `json_schema: {name, strict, schema}`, `max_completion_tokens`, e `temperature`/`seed`/`reasoning_effort` só quando não `None`.
3. Parâmetro de raciocínio: se `model` começa com `openai/gpt-oss`, enviar `include_reasoning: false`; se começa com `qwen/`, enviar `reasoning_format: "hidden"`; outros modelos, nenhum dos dois.
4. Cabeçalho `Authorization: Bearer <api_key>`; `Content-Type: application/json`.
5. Medir `latency_ms` com o `clock` injetado.
6. Classificar: 200 → sucesso; 400/413/422 → `REQUEST`; 401/403/404 → `CONFIGURATION`; 429 → `QUOTA` com `retry_after_seconds` do cabeçalho `retry-after`; 5xx → `TRANSIENT`; `httpx.TimeoutException` e `httpx.TransportError` → `TRANSIENT`.
7. 200 sem `choices[0].message.content` string não vazia → `INVALID_OUTPUT`. O provider **não** valida o schema (isso é do F20-14).
8. Ler os seis cabeçalhos `x-ratelimit-*` em toda resposta (inclusive erro) com `parse_duration` para os `reset-*`; valor inválido vira `None`.
9. `summary` do erro: status + primeiros 200 caracteres do corpo, com a chave removida se aparecer.
10. Escrever os testes com `httpx.MockTransport`.

## Exemplos

Requisição que o `GroqProvider` envia (`POST {GROQ_BASE_URL}/chat/completions`):

```json
{
  "model": "openai/gpt-oss-120b",
  "messages": [
    {"role": "system", "content": "<system.md do prompt>"},
    {"role": "user", "content": "<payload JSON renderizado>"}
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {"name": "analysis_v1", "strict": true, "schema": {"type": "object"}}
  },
  "max_completion_tokens": 900,
  "temperature": 0.2,
  "seed": 42,
  "reasoning_effort": "low",
  "include_reasoning": false
}
```

Para `qwen/qwen3.8-27b`, trocar `"include_reasoning": false` por `"reasoning_format": "hidden"`.
Nunca enviar os dois.

Resposta 200 (campos lidos):

```json
{
  "model": "openai/gpt-oss-120b",
  "choices": [{"message": {"role": "assistant", "content": "{\"summary\": \"...\"}"}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 2100, "completion_tokens": 422, "total_tokens": 2522,
            "prompt_time": 0.12, "completion_time": 0.81, "total_time": 0.93}
}
```

Cabeçalhos lidos em toda resposta: `x-ratelimit-limit-requests`, `x-ratelimit-limit-tokens`,
`x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`,
`x-ratelimit-reset-requests` (ex.: `2m59.56s`), `x-ratelimit-reset-tokens` (ex.: `7.66s`).
Em 429 também `retry-after` (segundos).

Os campos `*_time` de `usage` podem faltar: ausente vira `None`, nunca zero.

## Não fazer

- Não usar SDK do Groq nem da OpenAI.
- Não fazer retry aqui; retry é do router (F20-10).
- Não validar schema aqui; só extrair o texto.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Chamada 200 devolve `LLMResponse` com `usage` e `rate_limit` preenchidos.
- [x] Cada status da tabela e timeout/conexão vira o `ErrorKind` correto.
- [x] A chave não aparece em `repr`, em `summary` nem nos logs capturados.

## Testes

- `tests/backend/platform/ai/test_groq_provider.py`:
- `test_success_parses_content_usage_and_headers`
- `test_body_for_gpt_oss_sends_include_reasoning_false`
- `test_body_for_qwen_sends_reasoning_format_hidden`
- `test_status_mapping` (parametrizado: 400, 401, 403, 404, 413, 422, 429, 500, 503)
- `test_429_reads_retry_after`
- `test_timeout_and_transport_error_are_transient`
- `test_empty_content_is_invalid_output`
- `test_parse_duration` (parametrizado: `2m59.56s`, `7.66s`, `120ms`, `abc`, `None`)
- `test_api_key_never_in_repr_summary_or_logs` (usar `caplog`)

## Comando de verificação

```bash
docker compose -p f20-07 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/platform/ai/test_groq_provider.py
docker compose -p f20-07 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-07 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
