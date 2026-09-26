# CARD F20-16 — Identidade de cache com provedor e rota

- **Status:** Feito — `ANALYSIS_KEY_VERSION` subiu para `analysis-key-v3`; `GroqAnalysisAdapter.prepare` passa `model_id=route.chain[0]` e `options={"provider": "groq", "chain": ..., "reasoning_effort": ..., "max_completion_tokens": ..., "temperature": ..., "seed": ...}` ao `analysis_key`. Testes em `tests/backend/matching/test_groq_adapter.py`: `test_key_stable_for_same_inputs`, `test_key_changes_with_chain`, `test_key_changes_with_reasoning_effort`. Verificado com `docker compose -p f20-16 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_groq_adapter.py tests/backend/matching/test_analysis_persistence.py` (com `RUN_DATABASE_INTEGRATION=1`), `ruff check .` e `mypy` limpos.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-17
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §8.4; [F16-08](../../38-roadmap-ia-e-busca/fase-16/f16-08-cache-persistente.md)

## Resultado

Vaga, perfil, prompt, schema e rota de modelos iguais reaproveitam a análise gravada sem consumir quota; mudar qualquer um invalida o reuso.

## Contexto

O reuso persistente já existe: `matching/service.py:339-397` chama `adapter.prepare`, busca uma análise concluída com o mesmo `cache_key` e grava um `_reused_record`. A chave vem de `analysis_key(...)` em `matching/analysis.py:560` com `model_id`, `prompt_version`, `schema_version`, `prompt_digest`, `payload_hash` e `options`. `ANALYSIS_KEY_VERSION = "analysis-key-v2"`. O cache em memória `_AnalysisCache` do adapter antigo não é portado.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/matching/analysis.py` | `ANALYSIS_KEY_VERSION = "analysis-key-v3"` |
| Alterar | `src/opportunity_radar/matching/groq.py` | `options` do `analysis_key` com provedor e rota |
| Alterar | `tests/backend/matching/test_groq_adapter.py` | testes de chave |

## Passos

1. No `prepare` do `GroqAnalysisAdapter`, passar `model_id=route.chain[0]` e `options={"provider": "groq", "chain": list(route.chain), "reasoning_effort": ..., "max_completion_tokens": ..., "temperature": ..., "seed": ...}`.
2. Subir `ANALYSIS_KEY_VERSION` para `analysis-key-v3` (chaves antigas do Ollama nunca batem com as novas).
3. Gravar em `PreparedAnalysis.inference` o provedor e a cadeia; o modelo efetivo que respondeu vai no `SemanticAnalysis.model_id` (F20-17).
4. Escrever os testes.

## Não fazer

- Não criar tabela de cache nova: o reuso é pela análise gravada.
- Não portar `_AnalysisCache`.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Segunda análise idêntica não chama o provider nem reserva quota — reuso persistente em `matching/service.py` (F16-08, inalterado) pesquisa por `cache_key` antes de qualquer chamada; `test_key_stable_for_same_inputs` prova que o mesmo input sempre produz o mesmo `cache_key`.
- [x] Mudar modelo da rota, prompt, schema ou `reasoning_effort` muda o `cache_key` — `test_key_changes_with_chain`, `test_key_changes_with_reasoning_effort`.

## Testes

- `tests/backend/matching/test_groq_adapter.py`: `test_key_changes_with_chain`, `test_key_changes_with_reasoning_effort`, `test_key_stable_for_same_inputs`.
- `tests/backend/matching/test_analysis_persistence.py`: reuso sem chamada ao provider falso.

## Comando de verificação

```bash
docker compose -p f20-16 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/matching/test_groq_adapter.py tests/backend/matching/test_analysis_persistence.py
docker compose -p f20-16 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-16 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
