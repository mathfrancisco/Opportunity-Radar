# IA multiprovedor gratuita: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A análise de vagas continua funcionando quando o Groq esgota. Para isso, a cadeia de modelos passa a incluir Cerebras, OpenCode Zen, Token Harbor, Google (Gemma), OpenRouter, Mistral, NVIDIA NIM e Cloudflare Workers AI. Cada provedor tem sua própria cota, e um script de sondagem prova que cada modelo devolve JSON válido.

**Architecture:** Um registro declarativo (`ProviderSpec`) substitui a classe por provedor. Todos falam o protocolo de chat completions da OpenAI e herdam de `GroqProvider`. Os detalhes de cada provedor ficam em campos do spec, como o prefixo do modelo, a URL, o envio de `reasoning_effort`, o formato de resposta e os limites padrão. O `RoutedProvider` já roteia por prefixo; só passa a receber N backends. O `QuotaGuard` passa a resolver os limites por modelo, a partir do provedor dele. A IA liga com a chave de qualquer provedor, e não mais só com a do Groq.

**Tech Stack:** Python 3.12 + httpx (sem SDK de provedor) + SQLAlchemy + pydantic-settings + pytest; React 19 + Vitest em `apps/web` para dois textos.

**Spec:** `docs/research/2026-10-20-llm-gratuitos.md` (pesquisa e decisão). Contexto: SPEC 43 (`docs/43-*`), runbook `docs/30-runbook.md` §"Segundo provedor: Token Harbor".

## Global Constraints

- Nenhuma dependência nova. HTTP só com `httpx`, como `GroqProvider`.
- Toda chave é `SecretStr`. A chave nunca aparece em log, `repr`, `summary` de erro, telemetria, `/health` ou `make doctor`. O teste que já faz isso para o Groq (`_summary` redige a chave) vale para cada provedor.
- O texto enviado continua passando por `sanitize_for_llm`. Nenhum dado de contato do perfil sai.
- Modelos de provedores sem chave nunca entram na cadeia. Sem nenhuma chave, o estado é `blocked_by_configuration`, como hoje.
- Prefixos fixos: `cerebras:`, `zen:`, `tokenharbor:`, `gemini:`, `openrouter:`, `mistral:`, `nim:`, `workersai:`.
- Treino com os prompts é aceito (projeto pessoal, decisão do dono em 2026-10-20). O texto continua sanitizado, e `may_retain_prompts` só informa. Modelos do Groq continuam sem prefixo.
- Telemetria e cota identificam o modelo pelo nome com prefixo. O prefixo nunca chega à API.
- Sem migração: `platform.ai_quota_usage` já é por modelo.
- Comportamento atual preservado: com só `GROQ_API_KEY` (e opcionalmente `TOKENHARBOR_API_KEY`), as cadeias, os limites e as respostas do `/ai-budget` ficam idênticos aos de `origin/main`. Os testes atuais de `tests/backend/platform/ai/` passam sem edição, exceto os imports que a Task 1 move.
- Texto da UI: "vaga", nunca "oportunidade". Só afirmar o que é verdade: o texto não cita um provedor que pode não estar ligado.
- Backend: `ruff check .`, `mypy` e `pytest` dos módulos tocados. Integração com Postgres em container Linux (`pgvector/pgvector:0.8.6-pg17`, `RUN_DATABASE_INTEGRATION=1`), como o job `backend-tests` de `.github/workflows/pipeline.yml`. O venv do Windows não instala `uvloop`.
- Web: `npm run check` em `apps/web` com exit 0. Nunca rodar `npm install` local, e o `package-lock.json` não muda.
- Não ler `.env`. Nada de push, PR, merge, deploy ou criação de conta sem SIM do dono. As chaves reais só o dono coloca.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Groq sem chave e reservas com chave:** a IA liga. As cadeias não têm nenhum modelo sem prefixo, e `/health` fica `healthy`. Hoje `ai_status` exige `GROQ_API_KEY`. Teste na Task 2.
2. **Provedor sem cabeçalhos `x-ratelimit-*` e com `429` sem `Retry-After`** (Zen, Cerebras): o router bloqueia só aquele modelo pelo cooldown padrão e passa ao próximo. Nenhum outro provedor é bloqueado. Teste na Task 3.
3. **Teto interativo com provedor pequeno:** o worker chama com `ceiling_requests = day_requests - ai_interactive_reserve_requests` (750). Num provedor de 50/dia, o limite efetivo é `min(50, 750) = 50`, e o worker pode gastar tudo; a reserva interativa protege só o Groq. Ruling desta versão; o teste fixa esse comportamento na Task 3.
4. **Provedor que rejeita `response_format` `json_schema` com 400:** o spec com `response_format="json_object"` manda `{"type": "json_object"}` e mais nada. O validador e o reparo do router continuam valendo. Teste na Task 1.
5. **URL do Workers AI sem `account_id`:** o provedor fica fora da cadeia, com o motivo "falta CLOUDFLARE_ACCOUNT_ID" no `make doctor`. Uma URL `/accounts//ai/v1` nunca sai em requisição. Teste na Task 2.

---

### Task 1: Registro de provedores e provedor OpenAI-compatível genérico

Refatoração sem mudança de comportamento: Token Harbor passa a ser um `ProviderSpec`.

**Files:**
- Create: `src/opportunity_radar/platform/ai/providers/registry.py`
- Create: `src/opportunity_radar/platform/ai/providers/openai_compat.py`
- Delete: `src/opportunity_radar/platform/ai/providers/tokenharbor.py`
- Modify: `src/opportunity_radar/platform/ai/providers/routed.py`, `src/opportunity_radar/platform/ai/tasks.py:11,49-55,87`, `src/opportunity_radar/platform/ai/telemetry.py:25,118-120`, `src/opportunity_radar/presentation/http/dashboard.py:79,957`
- Test: `tests/backend/platform/ai/test_provider_registry.py` (novo); `tests/backend/platform/ai/test_tokenharbor_provider.py` (só os imports)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class ProviderSpec: name: str; prefix: str; default_base_url: str; reasoning_effort: bool; response_format: Literal["json_schema", "json_object"]; default_limits: QuotaLimits | None; provider_day_requests: int | None; may_retain_prompts: bool`
  - `TOKENHARBOR: ProviderSpec` e `PROVIDERS: tuple[ProviderSpec, ...]` em `registry.py`. Nesta task, `PROVIDERS == (TOKENHARBOR,)`, com `name="tokenharbor"`, `prefix="tokenharbor:"` (`reasoning_effort=True`, `response_format="json_schema"`, `default_limits=None`, `provider_day_requests=None`, `may_retain_prompts=True`).
  - `spec_for_model(model: str) -> ProviderSpec | None`: o spec cujo `prefix` inicia o nome; `None` para um modelo do Groq.
  - `provider_name_for(model: str) -> str`: `spec.name` ou `"groq"`.
  - `class OpenAICompatibleProvider(GroqProvider)`: `__init__(self, spec: ProviderSpec, *, api_key: str, base_url: str, timeout_seconds: float, connect_timeout_seconds: float, client_factory=None, clock=time.monotonic)`; `name = spec.name`. `_body` tira o prefixo, não envia `include_reasoning` nem `reasoning_format` (exclusivos do Groq), omite `reasoning_effort` quando `spec.reasoning_effort` é falso e troca `response_format` por `{"type": "json_object"}` quando `spec.response_format == "json_object"`. `complete` devolve `model=request.model`, com o prefixo.
  - `QuotaLimits` continua em `quota.py`. `registry.py` importa de lá. Se o mypy acusar import circular, mova `QuotaLimits` para `platform/ai/limits.py` e reexporte em `quota.py`.

- [ ] **Step 1: Escrever os testes que falham em `test_provider_registry.py`**

```python
def test_spec_for_model_matches_prefix_only():
    assert spec_for_model("tokenharbor:deepseek-v4.1-flash:free").name == "tokenharbor"
    assert spec_for_model("openai/gpt-oss-120b") is None
    assert provider_name_for("openai/gpt-oss-120b") == "groq"

def test_body_strips_prefix_and_groq_only_fields():
    spec = replace(TOKENHARBOR, prefix="x:")
    body = OpenAICompatibleProvider(spec, api_key="k", base_url="https://h/v1", timeout_seconds=1, connect_timeout_seconds=1)._body(_request("x:openai/gpt-oss-120b"))
    assert body["model"] == "openai/gpt-oss-120b"
    assert "include_reasoning" not in body and "reasoning_format" not in body
    assert body["response_format"]["type"] == "json_schema"

def test_json_object_spec_sends_plain_json_object():
    spec = replace(TOKENHARBOR, response_format="json_object", reasoning_effort=False)
    body = ..._body(_request("tokenharbor:m"))
    assert body["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in body

def test_error_summary_redacts_key():  # MockTransport devolve 401 com a chave no corpo
    with pytest.raises(ProviderError) as caught: ...
    assert "thk_live_test-key" not in str(caught.value)
```

- [ ] **Step 2:** Rodar `pytest tests/backend/platform/ai/test_provider_registry.py -q`. Esperado: FAIL com `ModuleNotFoundError: ...registry`.
- [ ] **Step 3:** Implementar `registry.py` e `openai_compat.py` com as interfaces acima. Apagar `tokenharbor.py`. Trocar `MODEL_PREFIX`/`TokenHarborProvider` por `spec_for_model`/`provider_name_for` em `routed.py`, `tasks.py`, `telemetry.py` e `dashboard.py`. Em `dashboard.py:957`, a condição vira `spec_for_model(name) is None`. Ajustar os imports de `test_tokenharbor_provider.py`.
- [ ] **Step 4:** Rodar `pytest tests/backend/platform/ai -q` e `ruff check . && mypy`. Esperado: tudo passa, e `test_tokenharbor_provider.py` passa sem mudar asserção.
- [ ] **Step 5:** Commit `refactor(ai): declarative provider registry over the OpenAI-compatible client`.

### Task 2: Novos provedores, configuração e "IA liga com qualquer chave"

**Files:**
- Modify: `src/opportunity_radar/platform/ai/providers/registry.py`, `src/opportunity_radar/platform/ai/providers/routed.py` (`build_provider`), `src/opportunity_radar/platform/ai/tasks.py` (`default_routes`), `src/opportunity_radar/platform/ai/config.py` (`ai_status`), `src/opportunity_radar/platform/health.py:45-56`, `src/opportunity_radar/platform/config.py:164-176`, o check `ai` do `make doctor` (onde ele lista modelo por papel), `.env.example:92-103`
- Test: `tests/backend/platform/ai/test_provider_registry.py`, `tests/backend/platform/ai/test_config.py`, `tests/backend/platform/ai/test_task_models.py`, o teste de `ai_health` existente

**Interfaces:**
- Consumes: `ProviderSpec`, `PROVIDERS`, `OpenAICompatibleProvider` (Task 1).
- Produces:
  - Settings novos, todos com padrão vazio ou desligado. Para cada `p` em `cerebras, zen, gemini, openrouter, mistral, nim, workersai`: `{p}_api_key: SecretStr = SecretStr("")`, `{p}_base_url: str = <default>` e `{p}_models: str = <default>`. Mais `cloudflare_account_id: str = ""`, `ai_reserve_order: str = "cerebras,zen,nim,tokenharbor,gemini,mistral,openrouter,workersai"` e `ai_provider_limits: dict[str, dict[str, int]] = {}` (JSON no env, chaves `minute_requests|minute_tokens|day_requests|day_tokens`).
  - Specs com estes valores (os limites viram `QuotaLimits(minute_requests, minute_tokens, day_requests, day_tokens)`):

    | name | prefix | base URL padrão | modelos padrão | reasoning_effort | default_limits | provider_day_requests | may_retain_prompts |
    |---|---|---|---|---|---|---|---|
    | cerebras | `cerebras:` | `https://api.cerebras.ai/v1` | `gpt-oss-120b,qwen-3.8-27b` | True | (4, 80_000, 900, 950_000) | None | False |
    | zen | `zen:` | `https://opencode.ai/inference/openai/v1` | `deepseek-v4.1-flash-free,glm-5.3-flash-free,minimax-m3.1-flash-free` | False | (20, 60_000, 300, 1_500_000) | None | False |
    | tokenharbor | `tokenharbor:` | `https://tokenharbor.ai/v1` | (setting atual) | True | None | None | True |
    | gemini | `gemini:` | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemma-4-31b-it` | False | (10, 60_000, 500, 1_000_000) | None | True |
    | openrouter | `openrouter:` | `https://openrouter.ai/api/v1` | `openai/gpt-oss-120b:free` | False | (15, 60_000, 45, 300_000) | 50 | True |
    | mistral | `mistral:` | `https://api.mistral.ai/v1` | `mistral-small-latest` | False | (20, 60_000, 500, 1_000_000) | None | True |
    | nim | `nim:` | `https://integrate.api.nvidia.com/v1` | `openai/gpt-oss-120b` | True | (30, 60_000, 1000, 1_000_000) | None | True |
    | workersai | `workersai:` | `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1` | `@cf/openai/gpt-oss-120b` | False | (20, 60_000, 40, 250_000) | None | False |

    Os valores de `reasoning_effort` e `response_format` são o palpite inicial. A Task 5 os confirma por sondagem.
  - `configured_providers(settings: Settings) -> list[tuple[ProviderSpec, str, str]]`: (spec, api_key, base_url) só dos provedores com chave, na ordem de `ai_reserve_order`, ignorando nomes desconhecidos. No `workersai`, `{account_id}` vem de `cloudflare_account_id`; sem ele, o provedor fica de fora.
  - `ai_status`: `ENABLED` se `ai_enabled` e (`groq_api_key` ou `configured_providers(settings)` não vazio).
  - `ai_health`: degraded `"no ai provider key"` em vez de `"groq api key missing"`.
  - `default_routes`: os papéis do Groq só entram com `groq_api_key`. Depois deles, os modelos de cada provedor configurado, na ordem, com o prefixo.
  - `build_provider`: se não há chave do Groq, o default do `RoutedProvider` é o primeiro provedor configurado, e nenhuma cadeia chega a ele por nome sem prefixo.

- [ ] **Step 1: Testes que falham**

```python
def test_reserve_chain_follows_order_and_skips_keyless():
    s = _settings(groq_api_key="g", cerebras_api_key="c", zen_api_key="z", ai_reserve_order="zen,cerebras,openrouter")
    chain = default_routes(s)[AITask.JOB_MATCH].chain
    assert chain == ("openai/gpt-oss-120b", "qwen/qwen3.8-27b",
                     "zen:deepseek-v4.1-flash-free", "zen:glm-5.3-flash-free", "zen:minimax-m3.1-flash-free",
                     "cerebras:gpt-oss-120b", "cerebras:qwen-3.8-27b")

def test_ai_enabled_without_groq_when_a_reserve_has_key():
    s = _settings(ai_enabled=True, cerebras_api_key="c")
    assert ai_status(s) is AIState.ENABLED
    assert all(m.startswith("cerebras:") for m in default_routes(s)[AITask.JOB_MATCH].chain)
    assert ai_health(s).status == "healthy"

def test_no_key_at_all_stays_blocked():
    assert ai_status(_settings(ai_enabled=True)) is AIState.BLOCKED_BY_CONFIGURATION
    assert ai_health(_settings(ai_enabled=True)).detail == "no ai provider key"

def test_workersai_without_account_id_is_left_out():
    s = _settings(workersai_api_key="w")
    assert [spec.name for spec, _, _ in configured_providers(s)] == []

def test_groq_only_routes_match_main():  # valores copiados de origin/main tasks.py
    assert default_routes(_settings(groq_api_key="g"))[AITask.JOB_CLASSIFICATION].chain == ("openai/gpt-oss-20b", "qwen/qwen3.8-27b")
```

- [ ] **Step 2:** Rodar os testes. Esperado: FAIL (settings inexistentes).
- [ ] **Step 3:** Implementar as interfaces. Em `.env.example`, um bloco por provedor com chave vazia e um comentário de uma linha (limite grátis, privacidade e link da pesquisa). O `make doctor` lista os provedores configurados por nome e quantidade de modelos, marca "pode reter prompts" quando `may_retain_prompts` é verdadeiro e dá o motivo de quem ficou de fora. Nunca mostra a chave.
- [ ] **Step 4:** Rodar `pytest tests/backend/platform/ai -q` mais os arquivos de teste de `ai_health` (`git grep -l ai_health tests`), `ruff check .` e `mypy`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(ai): Cerebras, OpenCode Zen, NIM, Gemma, Mistral, OpenRouter and Workers AI as reserve providers`.

### Task 3: Cota por provedor

**Files:**
- Modify: `src/opportunity_radar/platform/ai/quota.py` (`QuotaGuard.__init__`, `reserve`, os pontos de `self._limits` nas linhas ~216-240 e ~318-357), `src/opportunity_radar/worker.py:461-470`, `src/opportunity_radar/matching/adapters.py:58-70`
- Test: `tests/backend/platform/ai/test_quota.py`, `tests/backend/platform/ai/test_router.py`, `tests/backend/test_ai_quota_integration.py`

**Interfaces:**
- Consumes: `spec_for_model`, `ProviderSpec.default_limits`, `settings.ai_provider_limits` (Tasks 1-2).
- Produces:
  - `QuotaGuard(engine, limits: QuotaLimits, now=..., limits_for: Callable[[str], QuotaLimits] | None = None)`. Quando `limits_for` não é passado, todo modelo usa `limits` (comportamento atual). Todas as leituras de `self._limits` passam por `self._limits_of(model)`.
  - `limits_for_model(settings: Settings) -> Callable[[str], QuotaLimits]` em `registry.py`, com esta prioridade: override em `ai_provider_limits[spec.name]` (campo a campo) > `spec.default_limits` > os soft limits globais `AI_*` (Groq, Token Harbor).
  - Worker e adapter constroem o `QuotaGuard` com `limits_for=limits_for_model(settings)`.

- [ ] **Step 1: Testes que falham**

```python
def test_each_provider_has_its_own_day_limit(engine):  # integração
    guard = QuotaGuard(engine, GROQ_LIMITS, limits_for=lambda m: SMALL if m.startswith("openrouter:") else GROQ_LIMITS)
    for _ in range(SMALL.day_requests):
        assert guard.reserve("openrouter:m", 10) is not None
    assert guard.reserve("openrouter:m", 10) is None
    assert guard.reserve("openai/gpt-oss-120b", 10) is not None

def test_worker_ceiling_is_min_with_small_provider_limit(engine):
    guard = QuotaGuard(engine, GROQ_LIMITS, limits_for=lambda m: SMALL)
    taken = sum(guard.reserve("openrouter:m", 1, ceiling_requests=750) is not None for _ in range(SMALL.day_requests + 5))
    assert taken == SMALL.day_requests

def test_override_beats_spec_default():
    lf = limits_for_model(_settings(cerebras_api_key="c", ai_provider_limits={"cerebras": {"day_requests": 10}}))
    assert lf("cerebras:gpt-oss-120b").day_requests == 10
    assert lf("cerebras:gpt-oss-120b").minute_requests == 4

async def test_429_without_retry_after_blocks_only_that_model():  # test_router.py, fake provider
    # zen:a devolve 429 sem Retry-After; cerebras:b responde
    result = await router.run(AITask.JOB_MATCH, ...)
    assert result.response.model == "cerebras:b"
    assert router._is_blocked("zen:a") and not router._is_blocked("cerebras:b")
```

- [ ] **Step 2:** Rodar `pytest tests/backend/platform/ai/test_quota.py tests/backend/platform/ai/test_router.py -q` e a integração no container. Esperado: FAIL (`limits_for` inexistente).
- [ ] **Step 3:** Implementar. Não mexer no SQL: os limites já entram como parâmetros.
- [ ] **Step 4:** Rodar `pytest tests/backend/platform/ai tests/backend/test_ai_quota_integration.py -q` (no container), `ruff check .` e `mypy`. Esperado: PASS, inclusive o invariante de cota existente.
- [ ] **Step 5:** Commit `feat(ai): per-provider quota limits`.

### Task 4: Painel de orçamento e textos da UI por provedor

**Files:**
- Modify: `src/opportunity_radar/platform/ai/metrics.py:320-331` (`ai_budget`), `src/opportunity_radar/presentation/http/dashboard.py:935-975` (`get_ai_budget`, `_model_budget_response`, `ModelBudgetResponse`), `apps/web/src/components/AIBudgetCard.tsx:30,112`, `apps/web/src/routes/OverviewPage.tsx:472-513,817`, `apps/web/src/features/dashboard/api.ts` (tipo), `docs/30-runbook.md:335-365`
- Test: `tests/backend/dashboard/test_ai_budget.py`, `apps/web/src/components/AIBudgetCard.test.tsx`, `apps/web/src/routes/OverviewPage.test.tsx`, `apps/web/src/features/dashboard/api.test.ts`

**Interfaces:**
- Consumes: `limits_for_model`, `provider_name_for`, `ProviderSpec.provider_day_requests` (Tasks 1-3).
- Produces:
  - `ai_budget(..., limits_for: Callable[[str], QuotaLimits], provider_requests_limit_for: Callable[[str], int | None], ...)` substitui `requests_soft_limit`, `tokens_limit`, `provider_requests_limit` e `provider_limit_models`. Cada `ModelBudget` usa o limite do próprio modelo. `provider_requests_limit_for` devolve `settings.ai_provider_daily_requests_limit` para o Groq, `spec.provider_day_requests` para os demais e `None` quando o limite é desconhecido.
  - `ModelBudgetResponse` ganha `provider: str` (ex.: `"cerebras"`). O web mostra o nome do provedor ao lado do modelo, sem o prefixo.
  - Textos: "IA (Groq)" vira "IA na nuvem". "Bloqueada por configuração: falta a chave da Groq." vira "Bloqueada por configuração: nenhum provedor de IA tem chave.". A dica `hint` vira "IA indisponível, sem cota ou desligada".

- [ ] **Step 1: Testes que falham**

```python
def test_budget_uses_each_models_own_limit(engine):
    report = ai_budget(engine, state="enabled", models=["openai/gpt-oss-120b", "openrouter:x"],
                       limits_for=lambda m: SMALL if m.startswith("openrouter:") else GROQ_LIMITS,
                       provider_requests_limit_for=lambda m: 50 if m.startswith("openrouter:") else 1000, interactive_reserve_requests=100)
    by_model = {m.model: m for m in report.models}
    assert by_model["openrouter:x"].requests_limit == SMALL.day_requests
    assert by_model["openrouter:x"].provider_requests_limit == 50
```

```ts
it('não cita Groq quando falta chave', async () => {
  // AIBudgetCard com state 'blocked_by_configuration'
  expect(text).toContain('Bloqueada por configuração: nenhum provedor de IA tem chave.')
  expect(text).not.toMatch(/Groq/)
})
it('mostra o provedor ao lado do modelo, sem prefixo', ...)  // 'cerebras' e 'gpt-oss-120b', nunca 'cerebras:gpt-oss-120b'
```

- [ ] **Step 2:** Rodar `pytest tests/backend/dashboard/test_ai_budget.py -q` e `npx vitest run src/components/AIBudgetCard.test.tsx src/routes/OverviewPage.test.tsx`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. No runbook, a seção "Segundo provedor: Token Harbor" vira "Provedores de reserva". Ela traz uma tabela por provedor (env, limite grátis e data da leitura, privacidade) e a regra da cadeia, e diz que o Groq deixou de ser obrigatório.
- [ ] **Step 4:** Rodar `pytest tests/backend/dashboard -q` (no container), `ruff check .`, `mypy` e `npm run check` em `apps/web`. Esperado: PASS. Reportar arquivos, testes e JS gzip (limite 237,4 kB).
- [ ] **Step 5:** Commit `feat(ai): per-provider budget panel and provider-neutral copy`.

### Task 5: Script de sondagem dos provedores

**Files:**
- Create: `scripts/probe_ai_providers.py`
- Test: `tests/backend/test_probe_ai_providers.py`

**Interfaces:**
- Consumes: `configured_providers`, `OpenAICompatibleProvider`, `GroqProvider`, `default_routes` (Tasks 1-2).
- Produces: a CLI `python scripts/probe_ai_providers.py [--provider NAME] [--json PATH]`. Para cada modelo configurado, manda uma requisição fixa e sintética, sem nenhum dado de usuário: `system="Responda só JSON."`, `user="Classifique: 'Vaga de engenheira de dados, remoto, Brasil.'"`, um schema com `work_mode` enum `["remote","hybrid","onsite"]` e `max_completion_tokens=200`. Imprime uma linha por modelo: `provider model status latency_ms schema_ok rate_headers finish_reason`. `schema_ok` valida com o mesmo validador do router. Se a resposta for 400 com `json_schema`, tenta de novo com `json_object` e marca `json_object_only`. Exit 0 sempre que rodar; o resultado é dado, não teste. Nunca imprime a chave e não grava cota (não usa `QuotaGuard`).

- [ ] **Step 1: Testes que falham** (com `httpx.MockTransport`)

```python
def test_probe_marks_json_object_only_on_schema_400(): ...   # 1ª chamada 400, 2ª 200 válida → linha contém "json_object_only"
def test_probe_never_prints_key(capsys): ...                 # chave no corpo do erro 401 → ausente da saída
def test_probe_skips_unconfigured_providers(capsys): ...     # sem chave do openrouter → nenhuma linha "openrouter"
```

- [ ] **Step 2:** Rodar `pytest tests/backend/test_probe_ai_providers.py -q`. Esperado: FAIL.
- [ ] **Step 3:** Implementar. Documentar o uso no runbook, na seção da Task 4, numa linha.
- [ ] **Step 4:** Rodar os testes, `ruff check .` e `mypy`. Esperado: PASS.
- [ ] **Step 5:** Commit `feat(ai): provider probe script`.

### Task 6 (dono, com chaves reais): medir e decidir

Não é código. O executor prepara os comandos, e o dono roda na VM ou com o próprio `.env`.

- [ ] **Step 1:** Criar as contas e chaves: Cerebras (exige cartão verificado), OpenCode Zen, NVIDIA (build.nvidia.com) e Cloudflare (token com permissão Workers AI e `CLOUDFLARE_ACCOUNT_ID`). Opcionais: Google AI Studio, Mistral (aceitar o plano Experiment) e OpenRouter. Perguntar ao suporte do Zen (help@anoma.ly) se os modelos grátis podem ser usados por um backend de produto.
- [ ] **Step 2:** Rodar `python scripts/probe_ai_providers.py --json probe.json`. Para cada modelo com `schema_ok=false` ou `json_object_only`, corrigir `reasoning_effort` ou `response_format` no `ProviderSpec`, com um teste na Task 2. Registrar o resultado como Ruling.
- [ ] **Step 3:** Para cada modelo novo que passou, rodar `scripts/eval_analysis.py --model <modelo com prefixo>`. Comparar com `scripts/benchmark_report.py`. O dono preenche `human_review` (rubrica F20-22).
- [ ] **Step 4:** Decidir `AI_RESERVE_ORDER` e, se preciso, `AI_PROVIDER_LIMITS`, por medição. Um modelo com `label_accuracy` abaixo do Groq em mais de 10 pontos sai da cadeia de `job_match` e fica só em `job_classification` e `job_extraction`. Se isso acontecer, `default_routes` ganha a regra, com teste.
- [ ] **Step 5:** Deploy (com SIM): propagar as chaves novas para `api.env` e `worker.env` da VM (o mesmo caminho do F53, `prepare_envs.py`). Depois, `make doctor` mostra os provedores configurados, e `/ai-budget` lista os modelos novos.

## Fora deste plano

- Ollama na VM (self-host): a VM atual tem 8 GB. Só entra com uma medição em OCI A1 (24 GB) de latência por análise. Se o resultado for viável, vira um spec com `prefix="ollama:"` e um timeout maior, que exige um campo `timeout_seconds` no `ProviderSpec`.
- GitHub Models: descartado (fechado a novas contas). Modelos extras do Zen (Big Pickle, MiMo, Exo, LL Alpha) podem entrar só por `ZEN_MODELS`, sem código.
- Embeddings (SPEC 43 §9).
