# CARD F20-17 — `GroqAnalysisAdapter` na porta de análise

- **Status:** Feito — `matching/groq.py` implementa `GroqAnalysisAdapter` (prepare/analyze/warm_up/describe); `matching/adapters.py` monta `GroqProvider` + `QuotaGuard` + `CircuitBreaker` + `AIRouter` + o adapter; `worker.py`, `presentation/http/dependencies.py` e `operations/soak.py` ajustados para passar o `engine`. `tests/backend/matching/test_groq_adapter.py` (19 testes) e `tests/e2e/fake_groq.py` prontos. Verificado com `docker compose -p f20-17 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_groq_adapter.py tests/backend/matching/test_analysis_queue.py tests/backend/matching/test_analysis_persistence.py` (47 passed com `RUN_DATABASE_INTEGRATION=1`), `ruff check .` e `mypy` limpos.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-11, F20-12, F20-13, F20-14, F20-15
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §3

## Resultado

A análise da Inbox roda no Groq pelo mesmo `SemanticAnalysisPort`, com o prompt atual, com quota, breaker, sanitizer, orçamento e fallback ligados.

## Contexto

`SemanticAnalysisPort` (`matching/analysis.py:653`) exige `model`, `prompt_version`, `requires`, `prepare`, `analyze`, `warm_up` e `describe`. `OllamaAnalysisAdapter` (`matching/ollama.py`) já implementa `prepare` (linhas 177-332: montagem do payload, limpeza, orçamento, `evidence_sources`, chave) e `_user_content` (linhas 504-555). Esse código de `prepare` é **movido** para o adapter novo; o que é específico do Ollama (`_options`, `_chat_payload`, `_raise_for_status`, `_envelope`, `_content`, `_metrics`, `warm_up`, `describe`, `_keep_alive_seconds`) não é portado. O F20-04 apaga `ollama.py` depois.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `src/opportunity_radar/matching/groq.py` | `GroqAnalysisAdapter` |
| Alterar | `src/opportunity_radar/matching/adapters.py` | construir router, guard, breaker, provider e adapter |
| Criar | `tests/e2e/fake_groq.py` | servidor HTTP falso compatível (porta 8080, caminho `/openai/v1/chat/completions`) |
| Criar | `tests/backend/matching/test_groq_adapter.py` | testes |

## Interfaces

```python
class GroqAnalysisAdapter:
    def __init__(self, *, router: AIRouter, prompt: PromptArtifacts,
                 policy: AnalysisPolicy | None = None) -> None: ...
    @property
    def model(self) -> str: ...            # router.route(AITask.JOB_MATCH).chain[0]
    @property
    def prompt_version(self) -> str: ...   # prompt.version
    @property
    def requires(self) -> frozenset[str]: ...  # mesma regra do adapter antigo
    def prepare(self, request: AnalysisRequest) -> PreparedAnalysis: ...
    async def analyze(self, request: AnalysisRequest, *, prepared: PreparedAnalysis | None = None,
                      use_cache: bool = True) -> AnalysisOutcome: ...
    async def warm_up(self, *, only_if_idle: bool = False) -> AnalysisMetrics | None:
        return None                         # nada a aquecer na nuvem
    async def describe(self) -> Mapping[str, Any]:
        return {"provider": "groq", "chain": list(self._route.chain)}
```

## Passos

1. Criar `matching/groq.py` copiando `prepare`, `_ratio_and_margin` e `_user_content` de `matching/ollama.py`; trocar o orçamento `num_ctx` pelo `TaskBudget` (F20-13) e aplicar `sanitize_for_llm` (F20-15) no payload antes de renderizar.
2. `analyze`: se `policy.should_analyze` for falso → `AnalysisOutcome(AI_SKIPPED)`; se `prepared.overflow` → `AI_SKIPPED` com `CONTEXT_OVERFLOW`.
3. Chamar `router.run(AITask.JOB_MATCH, system=prepared.system, user=prepared.user_content, schema_name=f"analysis_{schema_version.replace('-', '_')}", json_schema=OUTPUT_SCHEMAS[schema_version], estimated_input_tokens=prepared.size.prompt_tokens_estimate or 0, ...)`, com o `validator` do F20-14.
4. Sucesso: `parse_analysis` do conteúdo, `model_id` = modelo que respondeu, `AnalysisMetrics(total_ms=latency_ms, prompt_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens, prompt_eval_ms=usage.prompt_ms, eval_ms=usage.completion_ms, load_ms=None, prompt_chars=..., prompt_tokens_estimate=...)` → `AI_COMPLETED`.
5. Mapear `ProviderError` → `AnalysisOutcome(AI_FAILED, failure_code=...)`: `QUOTA` → `QUOTA_EXHAUSTED`; `TRANSIENT` timeout → `TIMEOUT`, conexão → `TRANSPORT_ERROR`, 5xx → `SERVER_ERROR`; `INVALID_OUTPUT` → `SCHEMA_MISMATCH`; `CONFIGURATION` → `NOT_CONFIGURED`; `REQUEST` → `SERVER_ERROR` com detalhe "request rejected".
6. Em `adapters.py`, montar: `GroqProvider(api_key=..., base_url=..., timeouts)`, `QuotaGuard(engine, QuotaLimits(...))`, `CircuitBreaker(...)`, `AIRouter(provider, default_routes(settings), ...)`, `GroqAnalysisAdapter(router=..., prompt=load_prompt(settings.ai_analysis_prompt))`. `build_analysis_adapter` passa a receber o `engine`; ajustar os chamadores (`worker.py`, `presentation/http/dependencies.py`).
7. Criar `tests/e2e/fake_groq.py` (servidor `http.server` como o `fake_ollama.py` atual) que responde um JSON válido do schema v1 e cabeçalhos `x-ratelimit-*`.
8. Escrever os testes, incluindo o de corpo HTTP sem PII.

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

- Não apagar `matching/ollama.py` neste card (é o F20-04).
- Não mudar o prompt (F20-18).
- Não alterar `matching/service.py` além de passar o `engine` na construção do adapter.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Com o provider falso, uma análise vira `AI_COMPLETED` com `model_id`, tokens e latência gravados — `test_completed_records_model_tokens_latency`.
- [x] A saída nunca altera score, veredito, elegibilidade nem fator — `AnalysisOutcome`/`SemanticAnalysis` não declaram esses campos (`test_outcome_and_analysis_never_carry_score_or_verdict`); nenhum teste de matching mudou de comportamento.
- [x] Fallback para o modelo `alt` aparece no `model_id` gravado — `test_fallback_model_recorded`.
- [x] Corpo HTTP capturado não contém nenhum valor de PII do perfil de teste — `test_no_pii_in_http_body` (via `httpx.MockTransport` + `GroqProvider` real).
- [x] Quota esgotada → `AI_FAILED` com `QUOTA_EXHAUSTED` e sem chamada HTTP — `test_quota_exhausted_no_http_call`.

## Testes

- `tests/backend/matching/test_groq_adapter.py`: `test_completed_records_model_tokens_latency`, `test_fallback_model_recorded`, `test_skipped_by_policy`, `test_overflow_skipped_without_call`, `test_error_mapping` (parametrizado por `ErrorKind`), `test_no_pii_in_http_body`, `test_quota_exhausted_no_http_call`, `test_warm_up_returns_none`, `test_describe`.
- `tests/backend/matching/test_analysis_queue.py`: fila funciona com o adapter novo e provider falso.
- Teste de invariante: o assessment (score, verdict, eligibility, fatores) é idêntico antes e depois da análise.

## Comando de verificação

```bash
docker compose -p f20-17 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_groq_adapter.py tests/backend/matching/test_analysis_queue.py tests/backend/matching/test_analysis_persistence.py
docker compose -p f20-17 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-17 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
