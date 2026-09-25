# Opportunity Radar — Plano de LLMs 100% Cloud

> **Versão:** 2.0  
> **Data:** 25/09/2026  
> **Escopo desta versão:** somente a camada de IA/LLMs cloud.  
> **Fora de escopo por enquanto:** AWS, deploy, banco cloud, filas, observabilidade cloud e qualquer modelo local.

---

## 1. Objetivo

Migrar o Opportunity Radar para uma arquitetura de inferência **100% cloud**, sem Ollama e sem modelos executando no computador.

Objetivos principais:

- zero uso de CPU/GPU local para inferência;
- zero download de pesos de modelos;
- aproveitar Free Tiers e créditos;
- usar modelos maiores que os viáveis localmente;
- fallback automático entre provedores;
- outputs estruturados e validados;
- controlar requests e tokens;
- evitar dependência de um único fornecedor;
- permitir trocar de modelo sem alterar regras de negócio;
- criar base reutilizável para Interview Copilot, DevBrain, Finance Radar, Application Tracker e CV Intelligence.

---

# 2. Arquitetura alvo

```text
Opportunity Radar
       |
       v
   AI Service
       |
       v
    AI Router
       |
       +----------------------+---------------------+
       |                      |                     |
       v                      v                     v
     Groq                  Gemini               Fallbacks
       |                      |                     |
 GPT-OSS 120B          Gemini 3.8 Flash      Cerebras
 GPT-OSS 20B           Flash-Lite            OpenRouter
 Qwen 3.8 27B
```

Não existe mais:

```text
Ollama
localhost:11434
modelo local
GPU local
CPU local para inferência
download de pesos
```

---

# 3. Estratégia de providers

## Provider 1 — Groq

### Papel

Provider principal para a maior parte das análises do Opportunity Radar.

### Modelos

```text
openai/gpt-oss-120b
openai/gpt-oss-20b
qwen/qwen3.8-27b
```

### Uso recomendado

#### GPT-OSS 120B

Usar para:

- match candidato × vaga;
- análise técnica mais profunda;
- skill gap;
- interpretação de requisitos;
- geração de perguntas de entrevista;
- análise de evidências profissionais;
- decisões semânticas mais difíceis.

#### GPT-OSS 20B

Usar para:

- classificação;
- resumo curto;
- extração de campos;
- normalização;
- tarefas simples e frequentes.

#### Qwen 3.8 27B

Manter como alternativa dentro da própria Groq para:

- comparação de qualidade;
- classificação;
- structured extraction;
- fallback de modelo.

### Free Tier verificado em 25/09/2026

Para `openai/gpt-oss-120b`:

```text
30 RPM
1.000 requests/dia
8.000 tokens/minuto
200.000 tokens/dia
```

Os mesmos limites-base aparecem atualmente para GPT-OSS 20B e Qwen 3.8 27B no Free Plan.

### Pontos fortes

- excelente velocidade;
- modelos grandes;
- GPT-OSS 120B com contexto de 131.072 tokens;
- JSON Object Mode;
- JSON Schema Mode;
- reasoning;
- tool use;
- bom candidato para provider principal.

---

# 4. Provider 2 — Gemini

## Modelo principal

```text
gemini-3.8-flash
```

## Papel

Provider secundário e especializado em contexto grande.

Usar para:

- análise longa;
- currículo completo;
- descrição de vaga extensa;
- múltiplos documentos;
- contexto de carreira;
- análise profunda;
- fallback do Groq.

### Características atuais

Gemini 3.8 Flash possui:

```text
context window: ~1M tokens
max output: 64k
thinking configurável
structured outputs
function calling
```

### Free Tier

O Gemini API possui Free Tier para modelos elegíveis.

Os limites exatos podem variar por:

- projeto;
- modelo;
- conta;
- capacidade disponível.

Por isso a aplicação não deve fixar quotas do Gemini no código.

Consultar os limites ativos no Google AI Studio.

---

# 5. Gemini Flash-Lite

Para tarefas mais simples e em volume:

```text
gemini-3.1-flash-lite
```

ou o Flash-Lite mais recente disponível na conta.

Usos:

```text
classificação de vaga
extração de skills
normalização
resumos
tagging
detecção de idioma
```

Regra:

> usar modelos menores quando um modelo maior não aumenta significativamente a qualidade.

---

# 6. Provider 3 — Cerebras

## Papel

Provider experimental e de contingência.

Não será dependência crítica inicialmente.

Uso:

```text
benchmark
latência
comparação de modelos
fallback opcional
experimentos
```

### Crédito atual

A Cerebras anuncia atualmente:

```text
US$ 5 em crédito gratuito inicial
```

após criação de conta para o Inference Cloud.

### Por que adicionar

O principal interesse é:

- inferência extremamente rápida;
- APIs compatíveis com o padrão OpenAI;
- comparação direta com Groq;
- aprendizado de arquitetura multi-provider.

---

# 7. Provider 4 — OpenRouter

## Papel

Último fallback e laboratório de modelos.

### Free Plan atual

```text
50 requests/dia
25+ modelos gratuitos
```

Por causa desse limite, não deve ser provider principal.

### Uso recomendado

```text
fallback emergencial
experimentação
comparação entre modelos
```

---

# 8. Ordem padrão de fallback

```text
Groq
 |
 | erro / 429 / timeout / indisponibilidade
 v
Gemini
 |
 | erro
 v
Cerebras
 |
 | erro ou sem crédito
 v
OpenRouter
 |
 | erro
 v
PENDING / RETRY
```

Cerebras e OpenRouter podem ser desligados por configuração.

---

# 9. AI Router

Criar um único ponto de entrada.

```python
result = await ai_router.generate(
    task="job_match",
    payload=payload,
)
```

Nenhuma regra de negócio deve chamar Groq ou Gemini diretamente.

---

# 10. Interface base

```python
from typing import Protocol, Any


class LLMProvider(Protocol):

    async def generate(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        schema: type | None = None,
        temperature: float | None = None,
    ) -> Any:
        ...
```

Implementações:

```text
GroqProvider
GeminiProvider
CerebrasProvider
OpenRouterProvider
```

---

# 11. Estrutura sugerida

```text
app/
|
├── ai/
│   ├── router.py
│   ├── config.py
│   ├── tasks.py
│   ├── schemas.py
│   ├── exceptions.py
│   ├── retry.py
│   ├── metrics.py
│   │
│   ├── providers/
│   │   ├── base.py
│   │   ├── groq.py
│   │   ├── gemini.py
│   │   ├── cerebras.py
│   │   └── openrouter.py
│   │
│   └── prompts/
│       ├── job_match/
│       │   ├── v1.py
│       │   └── v2.py
│       ├── skill_gap/
│       ├── classification/
│       └── interview/
│
└── ...
```

---

# 12. Configuração

`.env.example`

```env
AI_PRIMARY_PROVIDER=groq
AI_SECONDARY_PROVIDER=gemini

GROQ_API_KEY=
GEMINI_API_KEY=
CEREBRAS_API_KEY=
OPENROUTER_API_KEY=

GROQ_REASONING_MODEL=openai/gpt-oss-120b
GROQ_FAST_MODEL=openai/gpt-oss-20b
GROQ_ALT_MODEL=qwen/qwen3.8-27b

GEMINI_REASONING_MODEL=gemini-3.8-flash
GEMINI_FAST_MODEL=gemini-3.1-flash-lite

AI_TIMEOUT_SECONDS=25
AI_MAX_RETRIES=2
AI_FALLBACK_ENABLED=true
```

Nunca commitar `.env`.

---

# 13. Tasks

Criar enum explícito:

```python
from enum import StrEnum


class AITask(StrEnum):
    JOB_CLASSIFICATION = "job_classification"
    JOB_EXTRACTION = "job_extraction"
    JOB_MATCH = "job_match"
    SKILL_GAP = "skill_gap"
    DEEP_ANALYSIS = "deep_analysis"
    CV_ANALYSIS = "cv_analysis"
    INTERVIEW = "interview"
```

---

# 14. Roteamento inicial

| Tarefa | Principal | Fallback |
|---|---|---|
| Job classification | Groq GPT-OSS 20B | Gemini Flash-Lite |
| Structured extraction | Groq GPT-OSS 20B | Gemini Flash-Lite |
| Job matching | Groq GPT-OSS 120B | Gemini 3.8 Flash |
| Skill gap | Groq GPT-OSS 120B | Gemini 3.8 Flash |
| Deep analysis | Gemini 3.8 Flash | Groq GPT-OSS 120B |
| CV analysis | Gemini 3.8 Flash | Groq GPT-OSS 120B |
| Interview | Groq GPT-OSS 120B | Gemini 3.8 Flash |
| Experimental | Cerebras | OpenRouter |

---

# 15. Não usar LLM quando não precisa

Regra central:

> deterministic first, LLM second.

Não gastar request para:

```text
data da vaga
salário numérico
vaga duplicada
texto contém "Brazil"
texto contém "remote"
URL duplicada
empresa já bloqueada
senioridade explicitamente incompatível
```

Python resolve isso.

LLM entra para:

```text
semântica
contexto
equivalência de skills
compatibilidade de experiência
interpretação de requisitos ambíguos
explicação
```

---

# 16. Pipeline de análise

```text
vaga
 |
 v
limpeza
 |
 v
regras determinísticas
 |
 v
extração
 |
 v
pré-score
 |
 v
AI Router
 |
 v
LLM
 |
 v
schema validation
 |
 v
resultado
```

---

# 17. Output estruturado

Evitar respostas livres para dados utilizados pelo sistema.

Exemplo:

```python
from pydantic import BaseModel, Field
from typing import Literal


class Eligibility(BaseModel):
    brazil_allowed: bool | None
    remote: bool | None
    confidence: float = Field(ge=0, le=1)


class JobMatch(BaseModel):
    track: Literal["java", "fullstack", "ai", "other"]

    match_score: int = Field(ge=0, le=100)

    eligibility: Eligibility

    matched_skills: list[str]
    missing_skills: list[str]

    strengths: list[str]
    concerns: list[str]

    explanation: str

    confidence: float = Field(ge=0, le=1)
```

Fluxo:

```text
LLM
 |
JSON Schema
 |
Pydantic
 |
valid object
```

---

# 18. Separar score de decisão do LLM

Não fazer:

```text
"LLM, dê uma nota de 0 a 100."
```

como única fonte.

Melhor:

```text
final_score
 |
 +-- deterministic score
 +-- semantic score
 +-- LLM evidence
```

Exemplo:

```text
skills                  30
experience              20
seniority               15
location                15
domain                   10
LLM evidence             10
---------------------------
total                   100
```

O LLM ajuda a interpretar.

Ele não deve controlar sozinho a decisão.

---

# 19. Prompt mínimo

Evitar mandar contexto desnecessário.

Ruim:

```text
currículo inteiro
+
todos os projetos
+
todo histórico
+
vaga
+
documentos
```

para toda requisição.

Melhor:

```text
vaga
+
perfil estruturado
+
experiências relevantes
```

---

# 20. Perfil estruturado

Criar uma representação sem PII:

```json
{
  "years_experience": 2,
  "tracks": [
    "java",
    "fullstack",
    "applied_ai"
  ],
  "skills": [
    "Python",
    "FastAPI",
    "Java",
    "Spring Boot",
    "TypeScript",
    "React",
    "PostgreSQL",
    "RAG",
    "LLMs"
  ],
  "experience": [
    {
      "role": "Software Engineer",
      "skills": [
        "Python",
        "FastAPI",
        "PostgreSQL"
      ],
      "evidence": [
        "..."
      ]
    }
  ]
}
```

Não precisa enviar:

```text
nome
email
telefone
endereço
CPF
```

---

# 21. PII Sanitizer

Antes de cada provider:

```text
payload
 |
 v
sanitize
 |
 v
prompt builder
 |
 v
provider
```

Criar função:

```python
def sanitize_for_llm(payload):
    ...
```

Remover pelo menos:

```text
e-mail
telefone
endereço
identificadores pessoais
segredos
tokens
API keys
```

---

# 22. Privacidade do Free Tier

Free Tiers podem possuir políticas diferentes de retenção e utilização de dados.

Portanto:

1. não mandar PII desnecessária;
2. não enviar segredos;
3. manter prompts profissionais minimizados;
4. revisar os termos de cada provider antes de produção;
5. tornar o provider configurável.

Especial atenção ao Gemini Free Tier: políticas de dados diferem dos serviços pagos.

---

# 23. Fallback inteligente

Fallback não deve acontecer para todo erro.

### Fazer fallback

```text
429
timeout
5xx
connection error
temporarily unavailable
```

### Não fazer fallback automaticamente

```text
401
403 por configuração
payload inválido
schema inválido causado pelo código
prompt quebrado
```

---

# 24. Retry

Exemplo:

```text
attempt 1
 |
 + 1s
 |
attempt 2
 |
 + 2s
 |
fallback provider
```

Adicionar jitter.

Não criar loop infinito.

---

# 25. Circuit breaker

Se um provider começar a falhar:

```text
Groq
 |
5 falhas consecutivas
 |
v
OPEN
```

Durante curto período:

```text
request
 |
v
Gemini
```

Depois testar novamente o provider primário.

---

# 26. Quota Guard

Criar controle interno.

Exemplo:

```python
FREE_TIER_GUARD = {
    "groq": {
        "daily_requests_soft_limit": 850
    },
    "openrouter": {
        "daily_requests_soft_limit": 40
    }
}
```

Usar valores abaixo do limite real.

Objetivo:

- deixar margem para testes;
- não bater no limite inesperadamente;
- evitar depender do último request disponível.

Para Gemini, ler os limites da conta e configurá-los externamente.

---

# 27. Token Guard

Definir budget por task.

```python
TASK_BUDGETS = {
    "job_classification": {
        "max_input_tokens": 1500,
        "max_output_tokens": 300
    },
    "job_match": {
        "max_input_tokens": 5000,
        "max_output_tokens": 900
    },
    "deep_analysis": {
        "max_input_tokens": 15000,
        "max_output_tokens": 1800
    }
}
```

Não mandar contexto infinito só porque o modelo suporta.

---

# 28. Cache de respostas

Mesmo sem definir infraestrutura agora, a camada de IA deve ser preparada para cache.

Cache key:

```text
hash(
 provider
 + model
 + prompt_version
 + schema_version
 + normalized_input
)
```

Se:

```text
vaga igual
+
perfil igual
+
prompt igual
```

não existe motivo para pagar/consumir quota novamente.

---

# 29. Prompt versioning

```text
prompts/
  job_match/
    v1.py
    v2.py
    v3.py
```

Resultado deve conhecer:

```json
{
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "prompt_version": "job_match_v3",
  "schema_version": "v2"
}
```

---

# 30. Telemetria interna

Registrar metadados:

```json
{
  "task": "job_match",
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "latency_ms": 932,
  "input_tokens": 2100,
  "output_tokens": 422,
  "success": true,
  "fallback_used": false,
  "prompt_version": "v3"
}
```

Nunca registrar:

```text
API key
token de autenticação
PII
currículo completo
prompt completo contendo dados pessoais
```

---

# 31. Métricas importantes

Acompanhar:

```text
requests/provider
requests/model
success rate
error rate
429 rate
fallback rate
average latency
p95 latency
input tokens
output tokens
JSON validity
schema errors
```

---

# 32. Dataset de avaliação

Criar:

```text
tests/ai_eval/
```

Começar com 50 vagas.

Depois:

```text
100
250
500
```

Cada item:

```json
{
  "id": "job_001",
  "input": {},
  "expected": {
    "track": "ai",
    "compatible": true,
    "score_min": 75,
    "score_max": 95
  }
}
```

---

# 33. Métricas de qualidade

Comparar os modelos com:

```text
classification accuracy
precision
recall
F1
JSON validity
false positive rate
false negative rate
latency
tokens
requests
```

---

# 34. Benchmark de providers

Criar:

```text
scripts/benchmark_llms.py
```

Executar o mesmo dataset em:

```text
Groq GPT-OSS 120B
Groq GPT-OSS 20B
Groq Qwen 3.8 27B
Gemini 3.8 Flash
Gemini Flash-Lite
Cerebras
```

Tabela:

```text
provider
model
task
accuracy
F1
latency
JSON validity
input tokens
output tokens
```

---

# 35. Seleção baseada em dados

Depois do benchmark:

```text
modelo melhor para matching
modelo melhor para classificação
modelo mais rápido
modelo mais econômico
modelo mais estável
```

O routing passa a refletir os resultados.

Não escolher modelo apenas por reputação.

---

# 36. Estratégia de implementação

## Fase 1 — remover Ollama

Remover do projeto:

```text
ollama
localhost:11434
Docker Ollama
downloads de modelos
config local model
```

Definition of Done:

- aplicação inicia sem Ollama;
- nenhum modelo é baixado;
- nenhuma chamada local de inferência existe.

---

# 37. Fase 2 — AIProvider

Criar:

```text
LLMProvider
AIRequest
AIResponse
AIError
```

Nenhuma dependência de provider no domínio.

---

# 38. Fase 3 — Groq

Implementar primeiro:

```text
GroqProvider
```

Configurar:

```text
GPT-OSS 120B
GPT-OSS 20B
Qwen 3.8 27B
```

Primeira task:

```text
job_match
```

---

# 39. Fase 4 — Structured Output

Criar:

```text
JobMatchSchema
JobClassificationSchema
SkillGapSchema
```

Validar todas as respostas com Pydantic.

---

# 40. Fase 5 — Gemini

Adicionar:

```text
GeminiProvider
```

Primeiro uso:

```text
fallback de job_match
```

Depois:

```text
deep_analysis
long_context
CV analysis
```

---

# 41. Fase 6 — AI Router

Implementar:

```python
await ai_router.generate(
    task=AITask.JOB_MATCH,
    payload=payload
)
```

Router escolhe automaticamente:

```text
provider
model
timeout
retry
fallback
```

---

# 42. Fase 7 — Quotas

Implementar:

```text
QuotaGuard
TokenGuard
```

Bloquear chamadas desnecessárias antes do provider.

---

# 43. Fase 8 — Cerebras

Criar adapter.

Uso inicial:

```text
benchmark
```

Depois decidir se entra na cadeia de fallback.

---

# 44. Fase 9 — OpenRouter

Criar adapter.

Uso:

```text
último fallback
laboratório
```

Nunca depender dele como provider principal no Free Plan.

---

# 45. Fase 10 — Evaluation

Criar dataset manual.

Rodar:

```text
provider x provider
model x model
prompt x prompt
```

---

# 46. Primeira entrega mínima

Não implementar tudo de uma vez.

Primeira PR:

```text
AIProvider
+
GroqProvider
+
JobMatchSchema
+
job_match prompt
```

Segunda PR:

```text
GeminiProvider
+
fallback
```

Terceira PR:

```text
AI Router
+
retry
+
quota guard
```

Quarta PR:

```text
evaluation
+
benchmark
```

---

# 47. Primeiro fluxo real

```text
POST /job-match
      |
      v
validate input
      |
      v
sanitize PII
      |
      v
deterministic preprocessing
      |
      v
AI Router
      |
      v
Groq GPT-OSS 120B
      |
      v
structured output
      |
      v
Pydantic validation
      |
      v
result
```

Fallback:

```text
Groq 429 / timeout / 5xx
       |
       v
Gemini 3.8 Flash
       |
       v
result
```

---

# 48. Resultado esperado

```json
{
  "track": "ai",
  "match_score": 84,
  "eligibility": {
    "brazil_allowed": true,
    "remote": true,
    "confidence": 0.94
  },
  "matched_skills": [
    "Python",
    "FastAPI",
    "PostgreSQL",
    "RAG"
  ],
  "missing_skills": [
    "Kafka"
  ],
  "strengths": [
    "Production experience with Python APIs",
    "Applied LLM/RAG experience"
  ],
  "concerns": [
    "Job asks for more distributed messaging experience"
  ],
  "explanation": "...",
  "confidence": 0.87
}
```

---

# 49. O que NÃO implementar agora

```text
AWS
Ollama
modelo local
GPU
fine-tuning
self-hosted inference
complex agent framework
multi-agent orchestration
vector database novo
Kubernetes
```

Primeiro provar:

```text
cloud LLM routing
structured output
fallback
quality
```

---

# 50. Evolução para os outros projetos

A camada será reutilizável.

```text
Opportunity Radar
       |
       v
Interview Copilot
       |
       v
DevBrain
       |
       v
Finance Radar
       |
       v
Application Tracker
       |
       v
CV Intelligence
```

---

# 51. Interview Copilot

Principal:

```text
Groq GPT-OSS 120B
```

Uso:

```text
perguntas
follow-ups
avaliação técnica
feedback estruturado
```

Gemini:

```text
vaga + currículo + histórico extenso
```

---

# 52. DevBrain

Gemini deve ter papel maior por contexto amplo.

Uso:

```text
documentos
notas
conteúdo extenso
síntese
```

A infraestrutura de retrieval será definida separadamente no futuro.

---

# 53. Finance Radar

LLM apenas para:

```text
classificação semântica
descrição de tendências
explicações
```

Nunca usar LLM para cálculo financeiro determinístico.

---

# 54. Application Tracker

LLM:

```text
resumir feedback
extrair motivo de rejeição
identificar padrões
classificar etapas
```

---

# 55. CV Intelligence

```text
vaga
+
evidências profissionais reais
       |
       v
LLM
       |
       v
sugestões fundamentadas
```

Regra absoluta:

> nunca inventar experiência, resultado, tecnologia ou responsabilidade.

---

# 56. Provider Strategy resumida

```text
                 AI ROUTER
                    |
       +------------+------------+
       |                         |
    FAST TASKS                HARD TASKS
       |                         |
Groq GPT-OSS 20B        Groq GPT-OSS 120B
       |                         |
       +------------+------------+
                    |
              NEED LONG CONTEXT?
                    |
             +------+------+
             |             |
            NO            YES
             |             |
           Groq      Gemini 3.8 Flash
                           |
                     failure/quota
                           |
                    fallback chain
```

---

# 57. Meta inicial de uso

### Groq

Usar como padrão.

Soft limits internos:

```text
<= 850 requests/dia
```

deixando margem para debug e testes.

### OpenRouter

Soft limit:

```text
<= 40 requests/dia
```

### Gemini

Configurar dinamicamente conforme a quota mostrada no AI Studio.

### Cerebras

Tratar os créditos gratuitos como laboratório.

---

# 58. Critérios para alterar provider

Só trocar o principal se os benchmarks mostrarem melhora relevante em:

```text
qualidade
latência
estabilidade
quota
custo
JSON validity
```

---

# 59. Definition of Done

A migração de LLM estará concluída quando:

- [ ] Ollama removido.
- [ ] Nenhum modelo local.
- [ ] Nenhum download de pesos.
- [ ] GroqProvider implementado.
- [ ] GeminiProvider implementado.
- [ ] Interface `LLMProvider` implementada.
- [ ] AI Router implementado.
- [ ] Job matching usando GPT-OSS 120B.
- [ ] Tarefas simples podendo usar modelo menor.
- [ ] Structured Outputs implementado quando suportado.
- [ ] Schemas Pydantic.
- [ ] Retry limitado.
- [ ] Fallback Groq → Gemini.
- [ ] Circuit breaker.
- [ ] Quota Guard.
- [ ] Token Guard.
- [ ] PII sanitizer.
- [ ] Prompt versioning.
- [ ] Logs de uso sem PII.
- [ ] Dataset de avaliação.
- [ ] Benchmark Groq × Gemini.
- [ ] Cerebras testado.
- [ ] OpenRouter opcional.
- [ ] `.env.example` atualizado.
- [ ] documentação atualizada.

---

# 60. Arquitetura final desta fase

```text
                    Opportunity Radar
                          |
                          v
                     AI Service
                          |
                          v
                      AI Router
                          |
              +-----------+-----------+
              |                       |
              v                       v
            Groq                    Gemini
              |                       |
      +-------+-------+          +----+----+
      |       |       |          |         |
   120B     20B     Qwen      3.8 Flash  Lite
      |
      +--------------------+
                           |
                        fallback
                           |
                 +---------+---------+
                 |                   |
              Cerebras           OpenRouter
```

**Nenhum modelo local faz parte desta arquitetura.**

---

# 61. Ordem prática para começar

```text
1. Criar chaves Groq e Gemini
2. Remover Ollama
3. Criar LLMProvider
4. Criar GroqProvider
5. Migrar job_match
6. Adicionar Pydantic
7. Criar GeminiProvider
8. Implementar fallback
9. Criar AI Router
10. Criar quotas internas
11. Criar dataset de avaliação
12. Rodar benchmark
13. Adicionar Cerebras
14. Adicionar OpenRouter
```

---

# 62. Fontes oficiais verificadas em 25/09/2026

## Groq

Rate limits:

https://console.groq.com/docs/rate-limits

Models:

https://console.groq.com/docs/models

GPT-OSS 120B:

https://console.groq.com/docs/model/openai/gpt-oss-120b

## Gemini

Pricing:

https://ai.google.dev/gemini-api/docs/pricing

Rate limits:

https://ai.google.dev/gemini-api/docs/rate-limits

Gemini 3.8 Flash:

https://ai.google.dev/gemini-api/docs/latest-model

## Cerebras

Inference:

https://www.cerebras.ai/inference

Pricing:

https://www.cerebras.ai/pricing

## OpenRouter

Pricing:

https://openrouter.ai/pricing

---

# 63. Observação final

Modelos, preços, quotas e Free Tiers mudam com frequência.

Por isso:

```text
provider != regra de negócio
model != hardcoded no domínio
quota != hardcoded permanentemente
```

Toda escolha deve ficar configurável.

A arquitetura correta é:

```text
Opportunity Radar
      |
AI Router
      |
providers substituíveis
```

Assim, se amanhã surgir um provider gratuito melhor, adicionamos um adapter e mudamos a política de roteamento sem reescrever o sistema.
