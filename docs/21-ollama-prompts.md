# Ollama, prompts e resultados estruturados

Este documento descreve o contrato da camada semântica. Ele complementa
`docs/20-matching-scoring.md` §37–§41 e §50, e o critério de aceite da Fase 6 em
`docs/29-roadmap-mvp.md` §46.

Estado: **adapter implementado (TASK-101)**. Os artefatos versionados de prompt
(`prompts/opportunity_analysis/v1/`) são entrega da TASK-102 e ainda não existem.

---

## 1. Princípio

A análise semântica é **consultiva**. O resultado determinístico é calculado antes,
persistido antes e nunca é sobrescrito pelo modelo.

```text
hard filters → score determinístico → threshold → (opcional) Ollama
```

Se o Ollama falhar, ficar indisponível ou devolver algo fora do schema, o
`MatchAssessment` continua completo. Apenas a camada semântica fica degradada.

---

## 2. Onde o código vive

| Arquivo | Papel |
|---|---|
| `src/opportunity_radar/matching/analysis.py` | contrato puro: value object, schema, cache key, política, porta |
| `src/opportunity_radar/matching/ollama.py` | adapter HTTP: `/api/chat`, timeout, retry, classificação de falha, cache |
| `src/opportunity_radar/platform/config.py` | configuração de runtime |
| `src/opportunity_radar/platform/health.py` | sinal degradado via `/api/tags` |

`analysis.py` não importa `httpx` e não conhece `/api/chat`. O domínio depende de
`SemanticAnalysisPort`, não do Ollama.

---

## 3. Contrato de saída

Schema fechado (`additionalProperties: false`), exportado como dado em
`OUTPUT_SCHEMA` para que a TASK-102 gere `output.schema.json` a partir da mesma
fonte em vez de duplicá-lo.

```json
{
  "summary": "string",
  "strengths": ["string"],
  "risks": ["string"],
  "inferences": ["string"],
  "unknowns": ["string"],
  "recommended_review": false
}
```

Nenhum campo de decisão existe no schema. `score`, `eligibility`, `verdict` e
`disqualifier` são **rejeitados** na validação — o modelo não consegue contrabandeá-los
para o estado persistido.

Limites: `summary` ≤ 2000 caracteres; cada lista ≤ 20 itens; cada item ≤ 500 caracteres.
Itens em branco são descartados; strings são normalizadas com `strip()`.

O adapter envia o schema no campo `format` do `/api/chat` e usa `temperature: 0`.

---

## 4. Estados de degradação

`AnalysisStatus` é o estado da camada semântica de um assessment cujas regras já
concluíram:

| Estado | Quando |
|---|---|
| `AI_COMPLETED` | JSON válido contra o schema |
| `AI_SKIPPED` | política decidiu não chamar o modelo |
| `AI_FAILED` | falha classificada (ver abaixo) |
| `AI_PENDING` | reservado para enfileiramento assíncrono (Fase posterior) |

`AnalysisFailureCode`:

| Código | Origem | Retentável |
|---|---|:--:|
| `TIMEOUT` | `httpx.TimeoutException` | sim |
| `TRANSPORT_ERROR` | `httpx.TransportError` (Ollama fora do ar) | sim |
| `MODEL_UNAVAILABLE` | HTTP 404 (modelo não instalado) | **não** |
| `RATE_LIMITED` | HTTP 429 | sim |
| `SERVER_ERROR` | HTTP 5xx e demais não-2xx | 5xx sim; outros não |
| `INVALID_JSON` | envelope ou conteúdo não parseável | sim |
| `EMPTY_RESPONSE` | `message.content` vazio | sim |
| `SCHEMA_MISMATCH` | JSON válido fora do contrato | sim |

`analyze()` **não levanta exceção** por falha externa: devolve `AnalysisOutcome`
classificado. Quem chama nunca precisa de `try/except` para manter o fluxo vivo.

---

## 5. Política de acionamento

Seção 50 do doc 20: o LLM é o recurso mais caro, então vem por último.

Padrão (`AnalysisPolicy`):

- pula quando `eligibility == INELIGIBLE`;
- pula quando `verdict ∈ {INELIGIBLE, LOW_MATCH}`;
- `minimum_score` configurável (padrão `0`).

Resultado do skip é `AI_SKIPPED`, não falha.

---

## 6. Cache

Chave (seção 40), em SHA-256 sobre JSON canônico:

```text
opportunity_id
opportunity_content_version
profile_version_id
rules_version
taxonomy_version
prompt_version
model_id
schema_version
```

Deliberadamente **fora** da chave: id do assessment, timestamp, score e verdict —
duas execuções sobre entradas equivalentes devem acertar a mesma entrada.

Qualquer mudança em um componente relevante é cache miss. Falhas nunca são cacheadas.
O cache atual é em memória e limitado (`ollama_analysis_cache_entries`, LRU).

## 7. Configuração

| Variável | Padrão | Papel |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | endpoint local |
| `OLLAMA_MODEL_ANALYSIS` | `llama3.2:3b` | modelo de análise |
| `OLLAMA_HEALTH_TIMEOUT_SECONDS` | `1.0` | timeout do healthcheck |
| `OLLAMA_ANALYSIS_ENABLED` | `true` | desliga a camada semântica |
| `OLLAMA_ANALYSIS_TIMEOUT_SECONDS` | `30.0` | timeout de leitura/escrita da análise |
| `OLLAMA_ANALYSIS_CONNECT_TIMEOUT_SECONDS` | `5.0` | timeout de conexão |
| `OLLAMA_ANALYSIS_MAX_RETRIES` | `1` | tentativas extras em falha retentável |
| `OLLAMA_ANALYSIS_RETRY_AFTER_SECONDS` | `0.5` | espera entre tentativas |
| `OLLAMA_ANALYSIS_CACHE_ENTRIES` | `256` | tamanho do cache em memória |

As quatro últimas ainda não estão listadas em `.env.example` (fora do escopo da
TASK-101); os padrões em `platform/config.py` cobrem a execução local.

---

## 8. Testes

`tests/backend/matching/test_analysis.py` cobre o contrato puro;
`tests/backend/matching/test_ollama_adapter.py` cobre o adapter com `httpx.MockTransport`.
Nenhum teste sobe modelo real, conforme §63 do doc 20.

Casos cobertos: JSON válido; JSON inválido; campo ausente; tipo
errado; campo fora do contrato; envelope malformado; conteúdo vazio; timeout; modelo
indisponível; 429/5xx; retry com sucesso; esgotamento do orçamento de retry; cache hit;
cache miss por versão de conteúdo; falha não cacheada; skip por política.

---

## 9. Pendente (TASK-102)

- `prompts/opportunity_analysis/v1/system.md`, `user.md.j2`, `output.schema.json`,
  `examples.json`, `metadata.yaml`;
- geração de `output.schema.json` a partir de `OUTPUT_SCHEMA`;
- persistência da análise junto ao `MatchAssessment` e exposição na API de
  explicabilidade.

O prompt embutido em `ollama.py` é mínimo e explícito, e existe apenas para o contrato
ser testável ponta a ponta até a TASK-102 substituí-lo por artefatos versionados.
