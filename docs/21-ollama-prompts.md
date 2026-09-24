# Ollama, prompts e resultados estruturados

Este documento descreve o contrato da camada semântica. Ele complementa
`docs/20-matching-scoring.md` §37–§41 e §50, e o critério de aceite da Fase 6 em
`docs/29-roadmap-mvp.md` §46.

Estado: **Fase 6 implementada**. O adapter veio na TASK-101; os artefatos versionados de
prompt, a persistência e a exposição na API vieram na TASK-102.

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
| `src/opportunity_radar/matching/prompts.py` | carga estrita dos artefatos versionados |
| `src/opportunity_radar/matching/ollama.py` | adapter HTTP: `/api/chat`, timeout, retry, classificação de falha, cache |
| `src/opportunity_radar/matching/models.py` | `matching.match_analysis`, histórico append-only |
| `src/opportunity_radar/matching/service.py` | `MatchingService.analyze`, reuso e persistência |
| `src/opportunity_radar/presentation/http/matching.py` | `POST /api/matches/{id}/analysis` |
| `src/opportunity_radar/platform/config.py` | configuração de runtime |
| `src/opportunity_radar/platform/health.py` | sinal degradado via `/api/tags` |

`analysis.py` não importa `httpx` e não conhece `/api/chat`. O domínio depende de
`SemanticAnalysisPort`, não do Ollama.

---

## 2.1 Artefatos versionados

```text
prompts/
└── opportunity_analysis/
    └── v1/
        ├── system.md
        ├── user.md.j2
        ├── output.schema.json
        ├── examples.json
        └── metadata.yaml
```

`prompts.py` recusa a carga quando:

- o diretório da versão não existe;
- algum artefato está vazio, ilegível ou mal formado;
- `output.schema.json` diverge de `OUTPUT_SCHEMA`;
- `metadata.yaml` declara `prompt_version` ou `schema_version` diferente do código;
- as variáveis declaradas em `metadata.yaml` não são exatamente as do template.

Na renderização, variável faltante e variável não usada também são erro. Um prompt que
perde silenciosamente um campo mudaria o comportamento do modelo sem mudar nenhum
validador.

`user.md.j2` mantém a extensão Jinja pelo layout documentado, mas apenas `{{ nome }}` é
suportado: o payload é um único documento JSON, então laços e condicionais só
acrescentariam dependência e não-determinismo. Cada valor é substituído já codificado em
JSON, e é isso que torna o template renderizado um JSON válido.

`output.schema.json` é gerado de `OUTPUT_SCHEMA`:

```bash
python scripts/export_prompt_schema.py           # regenera
python scripts/export_prompt_schema.py --check   # falha se estiver defasado (gate de CI)
```

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

São duas camadas:

| Camada | Escopo | Sobrevive a restart |
|---|---|:--:|
| LRU em memória do adapter (`ollama_analysis_cache_entries`) | processo | não |
| `matching.match_analysis` com `status = AI_COMPLETED` | banco | sim |

`MatchingService.analyze` consulta o banco antes de chamar o adapter. Só análise
concluída é reusada: `AI_FAILED` e `AI_SKIPPED` ficam registrados como histórico e não
bloqueiam nova tentativa. `refresh=true` força nova chamada e **acrescenta** uma linha.

---

## 6.1 Persistência

`matching.match_analysis` é append-only, com trigger que bloqueia `UPDATE`. Uma tentativa
degradada é evidência do que o sistema sabia naquele momento; repetir não pode apagá-la.
A análise corrente é a linha mais recente por `analyzed_at`.

A tabela não tem coluna de `score`, `verdict`, `eligibility` ou `disqualifier`. O modelo
não tem onde escrevê-los, então o critério "IA não sobrescreve disqualifier" é estrutural,
não uma regra de aplicação.

---

## 6.2 API

| Rota | Comportamento |
|---|---|
| `POST /api/matches/{id}/analysis` | executa ou reusa; corpo opcional `{"refresh": true}` |
| `GET /api/matches/{id}` | inclui `analysis` com a análise corrente, ou `null` |
| `GET /api/matches` | idem para cada item |

A rota responde `200` com o estado degradado quando o modelo falha; `404` apenas quando
o assessment não existe. Falha do Ollama não é erro HTTP: é `status` no corpo.

---

## 7. Configuração

| Variável | Padrão | Papel |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | endpoint local |
| `OLLAMA_MODEL_ANALYSIS` | `qwen3:8b-q4_K_M` | modelo de análise; a quantização vai na tag |
| `OLLAMA_HEALTH_TIMEOUT_SECONDS` | `1.0` | timeout do healthcheck |
| `OLLAMA_ANALYSIS_ENABLED` | `true` | desliga a camada semântica |
| `OLLAMA_ANALYSIS_TIMEOUT_SECONDS` | `60.0` | timeout de leitura/escrita da análise |
| `OLLAMA_ANALYSIS_CONNECT_TIMEOUT_SECONDS` | `5.0` | timeout de conexão |
| `OLLAMA_ANALYSIS_MAX_RETRIES` | `1` | tentativas extras em falha retentável |
| `OLLAMA_ANALYSIS_RETRY_AFTER_SECONDS` | `0.5` | espera entre tentativas |
| `OLLAMA_ANALYSIS_CACHE_ENTRIES` | `256` | tamanho do cache em memória |
| `OLLAMA_NUM_CTX` | `8192` | janela de contexto enviada em toda chamada |
| `OLLAMA_NUM_PREDICT` | `1024` | limite de tokens da resposta |
| `OLLAMA_SEED` | `42` | semente, para a mesma entrada dar a mesma saída |
| `OLLAMA_KEEP_ALIVE` | `30m` | quanto tempo o modelo fica carregado depois de uma chamada |
| `OLLAMA_THINK` | `false` | raciocínio do Qwen3; desligado na análise |

As variáveis do servidor (`OLLAMA_FLASH_ATTENTION`, `OLLAMA_KV_CACHE_TYPE`,
`OLLAMA_NUM_PARALLEL`, `OLLAMA_MAX_LOADED_MODELS`) são lidas pelo serviço `ollama` do
compose, não pela aplicação. A razão de cada valor está em `docs/36-spec-ollama.md`.

Todas estão em `.env.example` e em `compose.yaml`; os padrões em `platform/config.py`
cobrem a execução local sem configuração extra.

`OLLAMA_ANALYSIS_ENABLED=false` troca o adapter pelo `NullAnalysisAdapter`: a chamada
continua respondendo `200`, com `AI_SKIPPED`.

---

## 8. Testes

| Arquivo | Cobertura |
|---|---|
| `tests/backend/matching/test_analysis.py` | contrato puro |
| `tests/backend/matching/test_ollama_adapter.py` | adapter com `httpx.MockTransport` |
| `tests/backend/matching/test_prompts.py` | artefatos versionados e renderização |
| `tests/backend/matching/test_analysis_persistence.py` | persistência, reuso e degradação |

Nenhum teste sobe modelo real, conforme §63 do doc 20. No compose E2E, o stub em
`tests/e2e/fake_ollama.py` responde `/api/chat` com uma análise válida enquanto mantém
`/api/tags` vazio, então o ciclo completo é exercitado sem baixar modelo no CI.

Casos cobertos no contrato e no adapter: JSON válido; JSON inválido; campo ausente; tipo
errado; campo fora do contrato; envelope malformado; conteúdo vazio; timeout; modelo
indisponível; 429/5xx; retry com sucesso; esgotamento do orçamento de retry; cache hit;
cache miss por versão de conteúdo; falha não cacheada; skip por política.

Casos cobertos na persistência: análise concluída reusada sem segunda chamada; falha
registrada sem bloquear nova tentativa; camada desligada gerando `AI_SKIPPED`; `refresh`
acrescentando linha em vez de editar; score, verdict e fatores inalterados depois da
análise.

---

## 9. Fora do escopo desta fase

- fila assíncrona de análise (o estado `AI_PENDING` já existe para isso, mas hoje só o
  fluxo síncrono grava linhas);
- `prompts/opportunity_analysis/v2` e comparação entre versões de prompt;
- cache compartilhado entre processos além da própria tabela.
