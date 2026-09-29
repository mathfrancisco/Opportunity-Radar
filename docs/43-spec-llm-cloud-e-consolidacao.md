# SPEC — LLM cloud no Groq e consolidação das fases 16 a 19

- **Status:** Planejada; nenhuma capacidade nova abaixo é declarada entregue
- **Data:** 2026-09-25
- **Escopo:** (1) substituir o Ollama por inferência 100% cloud usando **apenas o Groq**;
  (2) reunir numa única fase — a **Fase 20** — tudo o que ficou pendente nas fases 16,
  17, 18 e 19
- **Cards de execução:** [Fase 20](44-roadmap-fase-20/README.md)
- **Origem:** [pesquisa de LLMs cloud](pesquisas/opportunity_radar_plano_llms_cloud.md)
- **Substitui:** a parte local da [SPEC 36 — Ollama](36-spec-ollama.md)
- **Continua valendo:** [SPEC 37 — Busca](37-spec-busca.md),
  [SPEC 39 — Varredura produtiva](39-spec-varredura-produtiva.md),
  [SPEC 41 — Tavily](41-spec-tavily.md), nos contratos que esta SPEC não altera

---

## 1. Objetivo

Tirar toda a inferência da máquina local. O radar deixa de depender de GPU, de
`ollama-init`, de download de pesos e de `keep_alive`. A análise semântica passa a ser
feita pelo Groq, com modelos maiores que os viáveis na RTX 5060, saída estruturada
validada, controle de quota e tokens, e o mesmo contrato de domínio que existe hoje.

Ao mesmo tempo, as fases 16 a 19 acumularam cards em revisão e em backlog espalhados em
quatro roadmaps. Esta SPEC fecha esse ciclo: uma fase, uma ordem, um conjunto de cards.

### 1.1 Simplificação em relação à pesquisa

A pesquisa propõe quatro provedores (Groq, Gemini, Cerebras, OpenRouter). Esta SPEC usa
**somente o Groq**. A porta `LLMProvider` continua existindo, para que outro provedor
entre depois como um adapter, sem mudar regra de negócio — mas nenhum outro adapter é
escrito nesta fase.

Consequências da simplificação:

- o fallback acontece **entre modelos do Groq**, não entre provedores; como as quotas do
  Free Plan são por modelo, trocar de modelo contorna 429 de um modelo específico;
- quando o Groq inteiro está indisponível, a análise fica pendente — o radar continua
  coletando, normalizando, avaliando e mostrando tudo, só sem o comentário (invariante
  herdada da Fase 16);
- o Groq não oferece modelo de embedding; ver §9.

## 2. Estado de partida

### 2.1 O que já existe e é reaproveitado

| Peça | Origem | Uso na Fase 20 |
| --- | --- | --- |
| `SemanticAnalysisPort`, `NullAnalysisAdapter`, `AnalysisRequest`, `SemanticAnalysis`, `Claim` | `matching/analysis.py` | contrato de domínio mantido; o adapter Groq implementa a mesma porta |
| Prompts versionados e `output_schema` | `matching/prompts.py` | reaproveitados; `v2` do F16-07 vira o prompt padrão no Groq |
| Orçamento de tokens e limpador | F16-05 (PR #20) | reaproveitado; estimativa recalibrada para o tokenizer dos modelos Groq |
| Harness de avaliação | F16-06, `scripts/eval_analysis.py` | reaproveitado; baselines refeitas no Groq |
| Identidade de análise e schema versionado | F16-08/F16-07 (`494fffd`) | reaproveitada; a chave passa a incluir provedor e modelo |
| Métricas da análise | F16-13 | reaproveitadas; ganham provedor, modelo, 429 e fallback |
| Área, full-text, normalização, completude | F17-02/03/06/07 | continuam; só falta aceite |

### 2.2 O que é descartado

| Card antigo | Motivo |
| --- | --- |
| F16-01 GPU, imagem e perfis | não há mais inferência local |
| F16-02 `qwen3:8b-q4_K_M` e opções | substituído pela escolha de modelo no Groq (F20-22) |
| F16-04 aquecimento e `keep_alive` | não se aplica a API cloud; a fila por valor migra para F20-24 |
| F16-09 embeddings locais | o Groq não tem embedding; ver §9 |
| F16-10 busca por significado, F16-11 RAG, F17-13 relevância aprendida | dependem de embedding; adiados para fora desta fase |
| F16-12 quantização | não se aplica; a confirmação de modelo vira F20-22 |

O aceite documental pendente de F16-01 a F16-04 não será feito: o código correspondente é
removido pelos cards F20-04 a F20-06.

## 3. Arquitetura alvo

```text
matching/service.py
        |
        v
SemanticAnalysisPort  (contrato de domínio, sem mudança)
        |
        v
GroqAnalysisAdapter
        |
        +-- sanitize_for_llm        (PII fora)
        +-- prompt builder          (prompt versionado, payload mínimo)
        +-- Token Guard             (orçamento por tarefa)
        +-- cache persistente       (identidade completa)
        +-- AI Router               (tarefa -> cadeia de modelos)
        |       |
        |       +-- Quota Guard     (RPM/RPD/TPM/TPD por modelo)
        |       +-- circuit breaker (por modelo)
        |       +-- retry com jitter
        |       v
        |   LLMProvider (porta)
        |       |
        |       v
        |   GroqProvider  -> https://api.groq.com/openai/v1/chat/completions
        |
        +-- validação Pydantic do JSON
        +-- telemetria sem PII
```

Ordem de troca: o adapter Groq é construído primeiro, movendo a lógica de `prepare` de
`matching/ollama.py`; só depois o Ollama é removido (F20-04 a F20-06). Assim o radar nunca
fica sem adapter no meio da fase.

Nada disso existe mais: `ollama`, `localhost:11434`, `ollama-init`, perfil `gpu` no
compose, download de pesos, `keep_alive`, `num_ctx`.

### 3.1 Estrutura de código

Para respeitar os contextos atuais, a camada fica em `platform` (infraestrutura
compartilhada) e o adapter de análise continua em `matching`:

```text
src/opportunity_radar/
  platform/ai/
    __init__.py
    tasks.py          # AITask
    config.py         # AISettings, ModelRoute, TaskBudget
    errors.py         # ProviderError e classificação (retryable, fallbackable, fatal)
    router.py         # AIRouter: cadeia de modelos, retry, breaker
    quota.py          # QuotaGuard
    breaker.py        # CircuitBreaker
    sanitizer.py      # sanitize_for_llm
    budget.py         # estimate_tokens, fits
    schema.py         # strict_compatible, make_validator
    telemetry.py      # AICallRecord e gravação
    metrics.py        # ai_metrics para API, Overview e doctor
    providers/
      base.py         # LLMProvider (Protocol), LLMRequest, LLMResponse, Usage
      groq.py         # GroqProvider (httpx)
  matching/
    groq.py           # GroqAnalysisAdapter: implementa SemanticAnalysisPort
    adapters.py       # build_analysis_adapter escolhe Groq ou Null
```

## 4. Provedor e modelos

Somente Groq, pela API compatível com OpenAI (`/openai/v1/chat/completions`), via
`httpx` — sem SDK novo, como os demais clientes HTTP do projeto.

| Papel | Modelo padrão | Uso |
| --- | --- | --- |
| `reasoning` | `openai/gpt-oss-120b` | match candidato × vaga, interpretação de requisito, análise difícil |
| `fast` | `openai/gpt-oss-20b` | classificação, extração, normalização ambígua, resumo curto |
| `alt` | `qwen/qwen3.8-27b` | fallback de modelo e comparação no benchmark |

Os nomes são configuração, nunca constante de domínio. A escolha final por tarefa sai do
benchmark (F20-22), não desta tabela.

### 4.1 Free Plan de referência (verificado em 2026-09-25)

| Modelo | RPM | RPD | TPM | TPD |
| --- | --- | --- | --- | --- |
| `openai/gpt-oss-120b` | 30 | 1.000 | 8.000 | 200.000 |
| `openai/gpt-oss-20b` | 30 | 1.000 | 8.000 | 200.000 |
| `qwen/qwen3.8-27b` | 30 | 1.000 | 8.000 | 200.000 |

Esses números **não** são fixados no código: entram como configuração com margem
(§7.1) e são corrigidos em tempo de execução pelos cabeçalhos de cada resposta.

### 4.2 Contrato da API (verificado na documentação oficial em 2026-09-25)

**Saída estruturada.** O corpo leva:

```json
{
  "response_format": {
    "type": "json_schema",
    "json_schema": { "name": "job_match_v2", "strict": true, "schema": { } }
  }
}
```

- `strict: true` (decodificação restrita, saída sempre no schema) é suportado pelos três
  modelos da §4: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.8-27b`;
- `strict: false` é melhor esforço e pode errar; `{"type": "json_object"}` só garante JSON;
- saída estruturada **não** combina com streaming nem com tool use; o radar não usa
  nenhum dos dois;
- `$defs` e recursão são aceitos, então o schema derivado do Pydantic pode ir direto.

**Raciocínio.**

| Modelo | `reasoning_effort` | Controle do texto de raciocínio |
| --- | --- | --- |
| GPT-OSS 20B e 120B | `low`, `medium`, `high` | `include_reasoning` (não aceita `reasoning_format`) |
| Qwen 3.8 27B | `none`, `default`, `low`, `medium`, `high` | `reasoning_format`: `parsed`, `raw`, `hidden` |

- `include_reasoning` e `reasoning_format` são mutuamente exclusivos; o provider envia só
  o que o modelo aceita (`include_reasoning: false` no GPT-OSS, `reasoning_format:
  hidden` no Qwen);
- tokens de raciocínio contam como saída e entram no `usage`, no Token Guard e na quota;
  por isso `reasoning_effort` padrão é `low` e sobe só com ganho medido no F20-22.

**Cabeçalhos de quota.** Sempre presentes: `x-ratelimit-limit-requests`,
`x-ratelimit-limit-tokens`, `x-ratelimit-remaining-requests`,
`x-ratelimit-remaining-tokens`, `x-ratelimit-reset-requests`,
`x-ratelimit-reset-tokens`. `retry-after` só vem em 429. O parser de `reset-*` aceita
duração em texto (ex.: `2m59.56s`, `7.66s`) e ignora valor que não entende, sem falhar a
chamada.

**Outros parâmetros usados:** `max_completion_tokens`, `temperature`, `seed`; resposta
com `usage.prompt_tokens` e `usage.completion_tokens`.

## 5. Configuração

`.env.example` (substitui todas as variáveis `OLLAMA_*`):

```env
AI_ENABLED=true
AI_PROVIDER=groq
GROQ_API_KEY=
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_REASONING_MODEL=openai/gpt-oss-120b
GROQ_FAST_MODEL=openai/gpt-oss-20b
GROQ_ALT_MODEL=qwen/qwen3.8-27b
AI_TIMEOUT_SECONDS=25
AI_CONNECT_TIMEOUT_SECONDS=5
AI_MAX_RETRIES=2
AI_FALLBACK_ENABLED=true
AI_REASONING_EFFORT=low
AI_ANALYSIS_PROMPT=v2
AI_DAILY_REQUESTS_SOFT_LIMIT=850
AI_DAILY_TOKENS_SOFT_LIMIT=170000
AI_MINUTE_TOKENS_SOFT_LIMIT=7000
AI_BREAKER_FAILURES=5
AI_BREAKER_COOLDOWN_SECONDS=120
```

Regras:

- sem `GROQ_API_KEY`, a análise é relatada como **bloqueada por configuração**, nunca como
  falha; o `NullAnalysisAdapter` assume e o resto do radar segue (mesma regra da Tavily);
- a chave nunca aparece em log, métrica, erro serializado, `doctor` nem resposta da API;
- `.env` nunca é commitado; o CI nunca chama o Groq real.

## 6. Tarefas e roteamento

```python
class AITask(StrEnum):
    JOB_MATCH = "job_match"                  # análise semântica atual (claims)
    JOB_CLASSIFICATION = "job_classification"  # área/senioridade ambíguas
    JOB_EXTRACTION = "job_extraction"        # campos estruturados de descrição
```

Rota inicial (cada modelo da cadeia é tentado na ordem; a troca obedece §7.3):

| Tarefa | Cadeia | `max_input_tokens` | `max_output_tokens` |
| --- | --- | --- | --- |
| `job_match` | reasoning → alt | 5.000 | 900 |
| `job_classification` | fast → alt | 1.500 | 300 |
| `job_extraction` | fast → reasoning | 3.000 | 600 |

Tarefas da pesquisa ligadas a outros produtos (skill gap isolado, entrevista, análise de
CV, DevBrain, Finance Radar) ficam fora desta fase. A porta e o enum aceitam novas
tarefas sem mudar o router.

### 6.1 Deterministic first

Nenhuma requisição é gasta com o que Python resolve: data, salário numérico, duplicata
por URL/chave, "remote"/"Brazil" explícitos, empresa bloqueada, senioridade
explicitamente incompatível, vaga inelegível. `job_classification` e `job_extraction` só
rodam quando a regra versionada deixou o campo `unknown`/ambíguo, e o resultado entra
como **sugestão com evidência**, nunca sobrescreve evidência de regra.

## 7. Confiabilidade

### 7.1 Quota Guard

- Contadores por modelo e por janela (minuto e dia UTC), persistidos no Postgres para
  sobreviver a reinício do worker e serem compartilhados entre API e worker.
- Limites internos abaixo do real (padrão: 850 req/dia, 170k tokens/dia, 7k tokens/min).
- Antes de cada chamada, o guard reserva a requisição e a estimativa de tokens; depois,
  ajusta pelo `usage` real.
- Os cabeçalhos `x-ratelimit-remaining-*` atualizam o saldo conhecido; o menor entre
  saldo interno e saldo informado vence.
- Modelo sem saldo é pulado na cadeia; cadeia inteira sem saldo deixa a análise pendente
  com motivo `quota_exhausted` e horário de retomada.

### 7.2 Token Guard

- Orçamento por tarefa (§6). O limpador do F16-05 corta a descrição com registro do
  corte; um prompt que ainda excede é recusado antes da chamada, sem gastar quota.
- `max_completion_tokens` sempre enviado.

### 7.3 Erros, retry e fallback

| Classe | Exemplos | Ação |
| --- | --- | --- |
| transitório | timeout, erro de conexão, 5xx, 503 | retry no mesmo modelo (até `AI_MAX_RETRIES`, backoff 1 s, 2 s com jitter), depois próximo modelo |
| quota | 429 | sem retry no mesmo modelo; respeita `retry-after`; próximo modelo |
| saída inválida | JSON fora do schema | uma tentativa de reparo no mesmo modelo; depois próximo modelo; conta em `schema_errors` |
| configuração | 401, 403, 404 de modelo | sem retry nem fallback; análise bloqueada por configuração; alerta no `doctor` |
| requisição | 400 por payload | sem retry nem fallback; falha registrada como defeito do código |

Nunca há laço infinito: o número máximo de chamadas por análise é
`len(cadeia) × (1 + AI_MAX_RETRIES)`.

### 7.4 Circuit breaker

Por modelo: `AI_BREAKER_FAILURES` falhas transitórias consecutivas abrem o circuito por
`AI_BREAKER_COOLDOWN_SECONDS`; depois uma chamada de prova (half-open) decide fechar ou
reabrir. 429 não abre o breaker — é tratado pelo Quota Guard.

## 8. Saída, privacidade e rastreabilidade

### 8.1 Saída estruturada

Cada tarefa tem um modelo Pydantic e o JSON Schema derivado dele vai no
`response_format`. A resposta é validada por Pydantic; os claims do `job_match`
continuam conferidos por código contra o texto da vaga e do perfil (regra do F16-07).

### 8.2 Score não é do modelo

A pesquisa sugere 10 pontos de "LLM evidence" no score. Esta SPEC **não adota** isso: a
invariante da Fase 16 continua — a saída do modelo nunca altera elegibilidade, score,
veredito nem fator. O modelo explica e sugere; a regra decide.

### 8.3 PII e dados que saem da máquina

A invariante antiga "nenhum dado sai da máquina" deixa de valer para a análise. No lugar:

- `sanitize_for_llm` roda antes de todo prompt e remove e-mail, telefone, endereço,
  CPF/documentos, URLs pessoais (LinkedIn/GitHub do candidato), tokens e chaves;
- o perfil enviado é o **perfil estruturado mínimo**: anos de experiência, trilhas,
  skills, experiências com cargo, skills e evidência — sem nome nem contato;
- um teste verifica que nenhum campo pessoal do perfil chega ao corpo HTTP;
- a documentação registra que o Free Plan pode ter retenção diferente do plano pago, e o
  operador liga a IA conscientemente (`AI_ENABLED` + chave).

### 8.4 Identidade e cache

A chave de cache é `hash(provider, model, prompt_version, schema_version,
payload_normalizado)`. O cache é persistente (fecha o F16-08). Vaga, perfil e prompt
iguais nunca consomem quota de novo. Toda análise grava provedor, modelo, versão de
prompt e de schema.

### 8.5 Telemetria

Cada chamada gera um `AICallRecord` sem PII: tarefa, provedor, modelo, latência, tokens
de entrada e saída, sucesso, classe de erro, tentativa, fallback usado, versão de prompt,
cache hit. Nunca: chave, prompt completo, currículo, resposta bruta.

Métricas expostas (API, Overview e `doctor`): requisições por modelo, taxa de sucesso,
taxa de 429, taxa de fallback, latência média e p95, tokens por dia, validade de JSON,
saldo da quota, estado do breaker.

## 9. Embeddings e pgvector

O Groq não oferece modelo de embedding. Com a restrição "apenas Groq":

- a geração de embedding local (F16-09, `qwen3-embedding`) é desligada e removida do
  worker junto com o Ollama;
- a extensão e a coluna pgvector **permanecem** no schema (dado derivado, sem custo);
  nenhuma migração destrutiva nesta fase;
- F16-10, F16-11, F17-13 e o sinal vetorial do F17-08 ficam fora da Fase 20; voltam
  quando houver um provedor de embedding aprovado, por um adapter novo.

## 10. Busca, varredura e Tavily

Os contratos das SPECs 37, 39 e 41 continuam valendo. A Fase 20 só reordena e renumera
os cards pendentes. Ajustes introduzidos por esta SPEC:

- F18-06 (análise útil sob orçamento) passa a ler o orçamento do Quota Guard em vez do
  custo de GPU — vira F20-24;
- a invariante "sem Ollama, a varredura continua" vira "sem Groq, a varredura continua";
- a Tavily continua um provedor separado de busca/extração, não de LLM.

## 11. Invariantes da Fase 20

- a saída do modelo nunca altera elegibilidade, score, veredito nem fator;
- sem chave, sem quota ou com o Groq fora do ar, o radar coleta, normaliza, avalia e
  mostra tudo, só sem o comentário;
- nenhuma chamada real ao Groq ou à Tavily roda no CI; os testes usam
  `httpx.MockTransport`;
- nenhuma PII nem segredo vai para o provedor ou para o log;
- nenhum modelo, quota ou nome de provedor fica fixo no domínio;
- toda troca de prompt, modelo ou `reasoning_effort` passa pelo conjunto de avaliação;
- os invariantes das fases 17, 18 e 19 (gate de homologação, coleta parcial não prova
  encerramento, teto de créditos Tavily) continuam em vigor.

## 12. Definition of Done da camada LLM

- [ ] Ollama, `ollama-init`, perfis de GPU e variáveis `OLLAMA_*` removidos.
- [ ] Nenhum modelo local, nenhum download de pesos.
- [ ] Porta `LLMProvider` e `GroqProvider` implementados.
- [ ] `GroqAnalysisAdapter` implementando `SemanticAnalysisPort`.
- [ ] AI Router com cadeia de modelos por tarefa.
- [ ] `job_match` no GPT-OSS 120B com prompt `v2`.
- [ ] Tarefas simples no GPT-OSS 20B, só para campo ambíguo.
- [ ] JSON Schema + Pydantic; claims conferidos por código.
- [ ] Retry limitado com jitter, fallback entre modelos, circuit breaker.
- [ ] Quota Guard persistente e Token Guard por tarefa.
- [ ] PII sanitizer com teste de corpo HTTP.
- [ ] Cache persistente com identidade completa.
- [ ] Telemetria sem PII; métricas na API, Overview e `doctor`.
- [ ] Baselines do conjunto de avaliação e benchmark 120B × 20B × Qwen registrados.
- [ ] `.env.example`, runbook e docs atualizados.

## 13. Fora de escopo

Gemini, Cerebras, OpenRouter e qualquer outro provedor; embeddings; AWS, deploy, banco
cloud, filas e observabilidade cloud; Interview Copilot, DevBrain, Finance Radar,
Application Tracker e CV Intelligence; fine-tuning; candidatura automática.

## 14. O que muda em cada fase com as LLMs cloud

### 14.1 Fase 16 — Camada local de IA

É a fase mais afetada: ela inteira foi escrita para o Ollama na RTX 5060.

| Card | Antes (local) | Com Groq | Destino |
| --- | --- | --- | --- |
| F16-01 GPU, imagem, perfis | Ollama 0.34.4, `ollama-init`, perfil GPU | não existe mais GPU nem imagem de modelo | removido por F20-04 a F20-06 |
| F16-02 modelo padrão e opções | `qwen3:8b-q4_K_M`, `num_ctx`, `num_predict`, `seed`, `think` | GPT-OSS 120B/20B, `max_completion_tokens`, `reasoning_effort` | substituído por F20-09 e F20-22 |
| F16-03 custo de cada análise | tempo de GPU e tokens locais | tokens e requisições contra a quota diária | absorvido por F20-19 e F20-20 |
| F16-04 aquecimento e fila por valor | `keep_alive`, modelo quente na VRAM | não há aquecimento; a fila por valor passa a proteger a quota | fila vai para F20-24; aquecimento some |
| F16-05 orçamento e limpador | corte para caber no `num_ctx` de 8.192 | corte para o orçamento por tarefa; estimativa calibrada pelo `usage` do Groq | F20-13 |
| F16-06 conjunto de avaliação | baselines na máquina de referência | mesmas métricas, rodadas contra o Groq real, fora do CI | F20-21 |
| F16-07 vaga no payload, prompt `v2` | enviava perfil inteiro sem risco | perfil mínimo e sanitizado; resto do escopo igual | F20-15 + F20-17 + F20-18 |
| F16-08 cache persistente | chave sem provedor | chave inclui provedor e modelo; hit não gasta quota | F20-16 |
| F16-09 pgvector e embeddings | `qwen3-embedding:0.6b` local | Groq não tem embedding; geração desligada, coluna mantida | fora da fase |
| F16-10, F16-11 | busca semântica e RAG | dependem de embedding | fora da fase |
| F16-12 modelo e quantização | escolher quantização na VRAM | escolher modelo e `reasoning_effort` por tarefa | F20-22 |
| F16-13 métricas | latência de GPU, fila | + provedor, modelo, 429, fallback, breaker, saldo | F20-19 e F20-20 |

Invariantes: "nenhum dado sai da máquina" é substituída por sanitizer + perfil mínimo;
"com o Ollama fora do ar" vira "sem chave, sem quota ou com o Groq fora do ar".

### 14.2 Fase 17 — Busca

A busca continua determinística; as LLMs cloud não entram no caminho da consulta.

| Card | Mudança |
| --- | --- |
| F17-01, 03, 04, 07 | nenhuma; só aceite pendente (F20-01 e F20-03) |
| F17-02 área da vaga, F17-06 normalização | regra continua decidindo; o GPT-OSS 20B pode **sugerir** valor quando a regra deixa `unknown` (F20-23); curadoria de `skills-v2` em F20-02 |
| F17-05, 09, 10, 11, 12 | nenhuma; renumerados F20-25, F20-27, F20-28 a F20-32 (um card por ATS), F20-33, F20-34 |
| F17-08 candidato a duplicata | perde o sinal vetorial previsto após F16-09 (F20-26) |
| F17-13 relevância aprendida | depende de embedding; fora da fase |

### 14.3 Fase 18 — Varredura produtiva

| Card | Mudança |
| --- | --- |
| F18-01 a F18-05 | nenhuma no escopo; renumerados F20-35 a F20-39 |
| F18-06 análise útil sob orçamento | orçamento deixa de ser tempo de GPU e passa a ser quota diária do Groq, com reserva para uso interativo (F20-24) |
| F18-07 preservação do perfil | passa a alimentar o perfil mínimo enviado ao Groq; parcial (`794b519`) (F20-40) |
| F18-08 backup | inclui as tabelas novas de quota, telemetria e cache (F20-41) |
| F18-09 prova do fluxo | relatório passa a incluir quota Groq, fallback e 429; dividido em F20-47 a F20-49 |

Invariante "sem Ollama, a varredura continua" vira "sem Groq, a varredura continua".

### 14.4 Fase 19 — Tavily

Nenhuma mudança de escopo: a Tavily é busca e extração, não LLM. Dois pontos de contato:

- a descrição extraída pela Tavily (F20-45) passa pelo mesmo limpador e orçamento de
  tokens antes de ir ao Groq;
- quota Groq e créditos Tavily aparecem juntos no relatório de custo do F20-49, mas com
  orçamentos independentes.

## 15. Fontes

- Groq rate limits: https://console.groq.com/docs/rate-limits
- Groq modelos: https://console.groq.com/docs/models
- GPT-OSS 120B: https://console.groq.com/docs/model/openai/gpt-oss-120b
- Pesquisa de origem: [opportunity_radar_plano_llms_cloud.md](pesquisas/opportunity_radar_plano_llms_cloud.md)
