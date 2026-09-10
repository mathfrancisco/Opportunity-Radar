# Roadmap do MVP e critérios de aceite

## 1. Objetivo

Este roadmap transforma a arquitetura do Opportunity Radar em uma sequência prática de implementação.

O objetivo não é apenas listar funcionalidades, mas definir:

- ordem;
- dependências;
- entregáveis;
- critérios de aceite;
- testes;
- riscos;
- gates de conclusão;
- o que explicitamente fica fora do MVP.

O MVP só é considerado concluído quando valida o ciclo completo:

```text
importar empresas
↓
configurar fontes
↓
coletar
↓
preservar RawItem
↓
normalizar
↓
deduplicar
↓
avaliar
↓
analisar com Ollama
↓
exibir
↓
acompanhar candidatura
```

---

## 2. Princípios do roadmap

### 2.1 Vertical slices

Evitar construir todos os bancos, depois todas APIs e só no fim integrar.

Preferir:

```text
uma capacidade pequena
→ ponta a ponta
→ testada
→ demonstrável
```

### 2.2 Gate antes de ampliar escopo

Só iniciar grande ampliação de fontes quando:

- persistência está estável;
- idempotência funciona;
- erros são observáveis;
- um collector está bem testado.

### 2.3 Infraestrutura mínima

MVP não inclui Redis/Celery apenas porque a arquitetura final inclui.

### 2.4 Toda fase precisa ser demonstrável

Cada fase termina com uma evidência objetiva.

---

## 3. Macrodependências

```mermaid
flowchart TD
    F0["Fase 0 Fundação"] --> F1["Fase 1 Perfil e Empresas"]
    F1 --> F2["Fase 2 Acquisition Framework"]
    F2 --> F3["Fase 3 Coletores reais"]
    F3 --> F4["Fase 4 Normalização e Oportunidades"]
    F4 --> F5["Fase 5 Matching"]
    F5 --> F6["Fase 6 Ollama"]
    F4 --> F7["Fase 7 Dashboard"]
    F5 --> F7
    F6 --> F7
    F7 --> F8["Fase 8 Pipeline"]
    F8 --> F9["Fase 9 Operação e Qualidade"]
    F9 --> DONE["MVP Done"]
```

---

# Fase 0 — Fundação

## 4. Objetivo

Criar um ambiente vazio, versionado e reproduzível.

---

## 5. Entregáveis

### Repositório

- estrutura base;
- README;
- `.gitignore`;
- `.dockerignore`;
- `.env.example`;
- convenções.

### Backend

- Python;
- FastAPI;
- Pydantic;
- SQLAlchemy;
- Alembic.

### Frontend

- React;
- TypeScript;
- Vite;
- Tailwind;
- Router;
- Query client.

### Infraestrutura

- PostgreSQL;
- Ollama;
- Compose;
- volumes;
- Makefile.

### Qualidade

- Pytest;
- frontend tests básicos;
- formatter/linter;
- type checks.

---

## 6. Tarefas

- [ ] criar estrutura de diretórios;
- [ ] configurar Python project;
- [ ] configurar Node project;
- [ ] criar container backend;
- [ ] criar container frontend;
- [ ] criar PostgreSQL;
- [ ] criar Ollama;
- [ ] criar `compose.yaml`;
- [ ] criar migrations iniciais;
- [ ] criar `/health/live`;
- [ ] criar `/health/ready`;
- [ ] criar `make up/down/logs/test`;
- [ ] validar persistência de volume.

---

## 7. Critério de aceite

Ambiente limpo:

```bash
docker compose up
```

precisa produzir:

```text
frontend disponível
API disponível
PostgreSQL healthy
worker/processo base disponível
Ollama ready ou degraded
```

Após reinício:

```text
dados de teste persistem
```

---

## 8. Gate

Não avançar se:

- migration só funciona manualmente no host;
- API depende de Postgres local instalado;
- `.env` contém secrets versionados;
- frontend usa endpoint hardcoded diferente por máquina.

---

# Fase 1 — Perfil e Empresas

## 9. Objetivo

Criar a base estável usada pelo matching e pela aquisição orientada a empresas.

---

## 10. Entregáveis de Profile

- `CareerProfile`;
- `ProfileVersion`;
- skills;
- experiências;
- projetos;
- preferências;
- endpoint de leitura;
- endpoint de atualização;
- ativação de versão.

---

## 11. Entregáveis de Company Radar

- `Company`;
- aliases;
- domínio;
- prioridade;
- `CompanySource`;
- status de verificação;
- listagem;
- busca.

---

## 12. Importação única do Notion

Criar:

```text
scripts/import_notion_export.py
```

Entradas:

```text
CSV
JSON
```

Flags:

```text
--input
--dry-run
--report
--resume
```

---

## 13. Regras do import

- normalizar nome;
- normalizar domínio;
- detectar aliases;
- detectar duplicatas;
- detectar colisão;
- registrar lote;
- permitir reexecução;
- não duplicar empresa;
- gerar relatório.

---

## 14. Cenários de teste

### Arquivo válido

```text
186 empresas
```

Resultado:

```text
186 reconciliadas
```

### Arquivo repetido

Resultado:

```text
0 duplicatas funcionais
```

### Empresa duplicada com alias

Resultado:

```text
1 Company
2 aliases
```

### Ambiguidade real

Resultado:

```text
manual_review_required
```

---

## 15. Critério de aceite

- [ ] dry-run não altera catálogo;
- [ ] import final funciona;
- [ ] reimport é idempotente;
- [ ] ambiguidades são reportadas;
- [ ] empresas aparecem na dashboard/API;
- [ ] token do Notion não é necessário depois da migração.

---

# Fase 2 — Framework de Acquisition

## 16. Objetivo

Construir a infraestrutura de coletores antes de implementar várias fontes.

---

## 17. Entregáveis

- `Collector` protocol;
- `CollectorRegistry`;
- `CollectorCapabilities`;
- `CollectionRequest`;
- `CollectedItem`;
- `SourceDefinition`;
- `SourceRun`;
- `RawItem`;
- checkpoints;
- error taxonomy.

---

## 18. Primeiro fluxo sem internet

Implementar `ManualCollector`.

Entrada:

```text
URL
texto
arquivo
```

Fluxo:

```text
manual
↓
CollectedItem
↓
RawItem
```

Isso valida arquitetura antes da dependência externa.

---

## 19. Persistência

Criar:

```text
acquisition.source_definition
acquisition.source_run
acquisition.raw_item
acquisition.source_checkpoint
```

Validar:

- timestamps;
- status;
- payload;
- hash;
- idempotência;
- correlation ID.

---

## 20. Critério de aceite

- [ ] SourceRun possui lifecycle;
- [ ] RawItem é preservado;
- [ ] repetição não duplica identidade externa;
- [ ] parser não cria Opportunity;
- [ ] erros possuem código estável;
- [ ] execução manual é visível na API.

---

# Fase 3 — Coletores reais

## 21. Objetivo

Validar o framework com múltiplas fontes de comportamentos diferentes.

---

## 22. Ordem recomendada

```text
1. Greenhouse
2. Lever
3. Ashby
4. uma fonte remota
```

A ordem pode mudar por disponibilidade, mas o MVP deve concluir três ATSs.

---

## 23. Para cada collector

Implementar:

- capabilities;
- configuration;
- identity;
- paginação;
- timeout;
- retry;
- rate limit;
- parser;
- fixtures;
- contract tests;
- métricas;
- error mapping.

---

## 24. Greenhouse

Gate:

```text
fixture
↓
parser
↓
CollectedItem
↓
RawItem
```

Depois teste real controlado.

---

## 25. Lever

Não reutilizar parser do Greenhouse.

Reutilizar apenas:

- contratos;
- HTTP infrastructure;
- resiliência;
- testes genéricos.

---

## 26. Ashby

Mesmo princípio.

Validar que novo collector não exige modificar domínio.

---

## 27. Fonte remota

Escolher uma das fontes previstas para o MVP.

Objetivo:

provar que o framework não funciona apenas para:

```text
jobs by company
```

mas também para:

```text
feed/query
```

---

## 28. Critério de aceite

Cada fonte:

- [ ] possui fixtures;
- [ ] contract tests;
- [ ] erros isolados;
- [ ] métricas;
- [ ] idempotência;
- [ ] timeout;
- [ ] retry;
- [ ] sem regra de matching;
- [ ] payload bruto salvo.

Globalmente:

```text
falha de uma fonte
≠
falha das outras
```

---

# Fase 4 — Normalização e Oportunidades

## 29. Objetivo

Transformar itens heterogêneos em oportunidades canônicas.

---

## 30. Entregáveis

- normalizador de título;
- normalizador de localização;
- work mode;
- seniority;
- contract type;
- compensation;
- skill extraction inicial;
- fingerprint;
- `Opportunity`;
- `SourceOccurrence`;
- merge;
- estados.

---

## 31. Pipeline

```text
RawItem
↓
parse result
↓
normalize fields
↓
external identity
↓
candidate fingerprint
↓
resolve identity
↓
Opportunity
↓
SourceOccurrence
```

---

## 32. Regras

Nunca perder:

```text
RawItem
SourceOccurrence
procedência
```

Mesmo quando duas ocorrências virarem uma única Opportunity.

---

## 33. Casos obrigatórios

### Mesmo external ID

```text
mesma source
mesmo external ID
```

→ mesma identidade externa.

### Mesma vaga em fontes diferentes

→ uma Opportunity, múltiplas occurrences quando resolver como equivalentes.

### Títulos semelhantes de empresas diferentes

→ oportunidades diferentes.

### Mesmo título, mesma empresa, datas distantes

→ não assumir automaticamente que é a mesma vaga.

---

## 34. Critério de aceite

- [ ] reprocessamento idempotente;
- [ ] duas fontes equivalentes podem gerar uma Opportunity;
- [ ] SourceOccurrences preservadas;
- [ ] fingerprint versionado;
- [ ] merge explicável;
- [ ] status funciona;
- [ ] procedência aparece na API.

---

# Fase 5 — Matching determinístico

## 35. Objetivo

Criar recomendação útil antes de integrar IA.

---

## 36. Entregáveis

- `OpportunitySnapshot`;
- `ProfileSnapshot`;
- specifications;
- hard filters;
- `EligibilityResult`;
- `MatchingRuleSet`;
- pesos;
- missing policies;
- `MatchAssessment`;
- `MatchFactor`;
- verdicts;
- confidence;
- evidências.

---

## 37. Ordem de implementação

### Passo 1

Implementar Specifications:

```text
Active
RemoteCompatible
CountryAllowed
WorkAuthorizationCompatible
TimezoneCompatible
SeniorityCompatible
ContractCompatible
```

### Passo 2

Implementar score.

### Passo 3

Persistir fatores.

### Passo 4

Criar API explicável.

---

## 38. Testes

Criar golden dataset.

Casos:

```text
perfect_match
missing_salary
incompatible_country
ambiguous_seniority
partial_skills
old_job
```

---

## 39. Critério de aceite

Mesmas entradas + mesma versão de regras:

```text
mesmo score
mesmo verdict
mesmas explicações
```

Além disso:

- [ ] hard disqualifier domina verdict;
- [ ] score fica 0–100;
- [ ] fatores somam corretamente;
- [ ] UNKNOWN não vira FALSE implicitamente;
- [ ] nenhum atributo sensível entra no score.

---

# Fase 6 — Ollama

## 40. Objetivo

Adicionar análise semântica sem comprometer o determinismo.

---

## 41. Entregáveis

- Ollama adapter;
- model configuration;
- prompt versionado;
- JSON Schema;
- retry;
- timeout;
- cache;
- estados de degradação.

---

## 42. Prompt

Estrutura:

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

---

## 43. Pipeline

```text
eligible/relevant opportunity
↓
build prompt
↓
Ollama
↓
validate JSON
↓
persist semantic analysis
```

---

## 44. Falha

Se Ollama estiver indisponível:

```text
MatchAssessment rules = concluído
AI = pending/failed
```

Nenhuma vaga é perdida.

---

## 45. Cache

A chave deve considerar:

```text
opportunity content version
profile version
rules version
prompt version
model
schema version
```

---

## 46. Critério de aceite

- [ ] resposta válida segue schema;
- [ ] JSON inválido é tratado;
- [ ] timeout é tratado;
- [ ] modelo indisponível não derruba fluxo;
- [ ] cache evita repetição idêntica;
- [ ] IA não sobrescreve disqualifier.

---

# Fase 7 — Dashboard

## 47. Objetivo

Tornar o sistema operacional sem depender de SQL ou scripts.

---

## 48. Telas mínimas

```text
Overview
Opportunity Inbox
Opportunity Detail
Companies
Sources / Executions
Profile / Preferences
Pipeline
```

---

## 49. Overview

Mostrar:

```text
novas oportunidades
high priority
recommended
sources failing
applications active
follow-ups próximos
```

---

## 50. Opportunity Inbox

Filtros:

- verdict;
- score;
- empresa;
- data;
- work mode;
- status;
- aplicada/não aplicada.

Ordenação:

```text
priority
recency
score
```

---

## 51. Opportunity Detail

Precisa mostrar:

- título;
- empresa;
- localização;
- modalidade;
- descrição;
- fontes;
- evidências;
- score;
- fatores;
- missing requirements;
- disqualifiers;
- semantic analysis;
- versões relevantes;
- ação de iniciar candidatura.

---

## 52. Companies

Mostrar:

- empresa;
- prioridade;
- aliases;
- domínio;
- sources;
- última verificação;
- últimas vagas.

---

## 53. Sources / Executions

Mostrar:

- fonte;
- enabled;
- último run;
- status;
- duração;
- itens;
- erro;
- executar manualmente.

---

## 54. Profile

Editar:

- skills;
- preferências;
- países;
- work mode;
- contratos;
- timezone;
- remuneração.

Alteração relevante cria nova versão.

---

## 55. Estados de UI

Toda tela crítica precisa considerar:

```text
loading
empty
error
partial/degraded
success
retry
```

---

## 56. Critério de aceite

Usuário consegue:

```text
abrir dashboard
↓
filtrar vagas
↓
abrir recomendação
↓
entender score
↓
ver evidência
↓
iniciar candidatura
↓
ver saúde das fontes
```

sem acessar terminal.

---

# Fase 8 — Pipeline básico

## 57. Objetivo

Acompanhar candidaturas sem implementar ainda CRM avançado.

---

## 58. Entregáveis

- `ApplicationProcess`;
- `StageHistory`;
- estágios;
- next action;
- notas;
- follow-up básico.

---

## 59. Estágios iniciais

Exemplo:

```text
INTERESTED
APPLIED
SCREENING
INTERVIEW
TECHNICAL
FINAL
OFFER
REJECTED
WITHDRAWN
CLOSED
```

A lista exata deve alinhar-se ao documento de workflows.

---

## 60. Regras

- uma candidatura ativa por opportunity/profile;
- transições válidas;
- histórico imutável;
- current stage derivado/atualizado consistentemente;
- oportunidade e candidatura continuam conceitos distintos.

---

## 61. Critério de aceite

- [ ] iniciar candidatura;
- [ ] mudar estágio;
- [ ] histórico permanece;
- [ ] próxima ação pode ser definida;
- [ ] filtro da Inbox sabe se vaga já foi aplicada;
- [ ] restart preserva pipeline.

---

# Fase 9 — Operação e qualidade

## 62. Objetivo

Garantir que o MVP seja utilizável continuamente, não apenas demonstrável uma vez.

---

## 63. Entregáveis

- logs estruturados;
- doctor;
- backup;
- restore check;
- E2E;
- documentação;
- runbook;
- smoke test;
- testes de ambiente limpo.

---

## 64. Cenário E2E obrigatório

```text
empty environment
↓
docker compose up
↓
import 186 companies
↓
run collectors
↓
normalize
↓
dedupe
↓
match
↓
Ollama
↓
Inbox
↓
open opportunity
↓
start application
↓
restart
↓
state preserved
```

---

## 65. Backup gate

```text
make backup
↓
arquivo criado
↓
make restore-check
↓
novo DB
↓
smoke queries
```

Somente criar dump não atende o critério.

---

## 66. Critério de aceite

- [ ] logs identificam falhas;
- [ ] source error não derruba sistema;
- [ ] restore funciona;
- [ ] runbook funciona;
- [ ] E2E passa;
- [ ] máquina limpa consegue executar;
- [ ] documentação corresponde ao comportamento real.

---

# 67. Recorte explícito do MVP

Não entram obrigatoriamente:

```text
Redis
Celery
Celery Beat
outbox distribuído
outreach avançado
envio automático
propostas completas
simulador de entrevistas completo
projeções assíncronas materializadas
dezenas de fontes
Kubernetes
Kafka
Elasticsearch
vector DB dedicado
GraphQL
```

Esses itens podem existir como arquitetura futura, não como blocker do MVP.

---

# 68. O que NÃO cortar do MVP

Mesmo reduzido, não remover:

- RawItem;
- procedência;
- dedupe;
- hard filters;
- explicabilidade;
- versionamento básico;
- migrations;
- idempotência;
- healthchecks;
- backup;
- teste de restore;
- contratos dos collectors.

Cortar esses itens tornaria o MVP rápido de demonstrar, mas caro de evoluir.

---

# 69. Matriz de dependência resumida

| Item | Depende de |
| --- | --- |
| Import Notion | DB + Company model |
| Collector | Acquisition framework |
| Opportunity | RawItem/normalização |
| Matching | Opportunity + Profile |
| Ollama | Matching básico |
| Inbox | Opportunity + Matching |
| Pipeline | Opportunity |
| Operations | SourceRun/jobs |
| Backup | PostgreSQL/Compose |
| E2E | todas as fases |

---

# 70. Priorização MoSCoW

## Must

- importação;
- empresas;
- três ATSs;
- uma fonte remota;
- entrada manual;
- RawItem;
- Opportunity;
- dedupe;
- hard filters;
- score;
- Ollama;
- Inbox;
- detail;
- pipeline básico;
- Docker;
- backup;
- testes essenciais.

## Should

- CompanySource verification;
- scheduler configurável;
- retries;
- filtros avançados;
- follow-up básico;
- operations screen.

## Could

- generator Boolean integrado;
- mais remote boards;
- métricas avançadas;
- pg_trgm;
- materialized views.

## Won't — MVP

- envio automático;
- microsserviços;
- Kubernetes;
- dezenas de integrações.

---

# 71. Estratégia de branches/entregas

Cada incremento deve ser pequeno.

Exemplo:

```text
feature/profile-versioning
feature/company-import
feature/acquisition-core
feature/collector-greenhouse
feature/opportunity-dedup
feature/matching-rules
feature/ollama-adapter
feature/opportunity-inbox
```

Cada branch/PR deve possuir:

- objetivo;
- migrations;
- testes;
- screenshots quando UI;
- docs alteradas.

---

# 72. Definition of Done por item

Uma tarefa funcional só está pronta quando aplicável:

- [ ] código implementado;
- [ ] type checks;
- [ ] lint;
- [ ] unit tests;
- [ ] integration test;
- [ ] migration;
- [ ] error handling;
- [ ] logs;
- [ ] documentação;
- [ ] critério demonstrável;
- [ ] nenhuma regressão de idempotência.

---

# 73. Definition of Ready

Antes de iniciar item:

- comportamento conhecido;
- dependências concluídas;
- contrato de entrada/saída definido;
- casos de erro principais identificados;
- teste de aceite descrito.

Isso reduz retrabalho de implementar endpoint antes de definir modelo.

---

# 74. Riscos do roadmap

## Risco 1 — investir cedo demais em fontes

Mitigação:

```text
framework + 1 collector bem feito
antes de 10 collectors
```

## Risco 2 — IA virar núcleo do sistema

Mitigação:

```text
matching determinístico primeiro
```

## Risco 3 — dedupe tardio

Mitigação:

implementar antes de volume real.

## Risco 4 — modelagem muito genérica

Mitigação:

queries reais desde cedo.

## Risco 5 — UI construída antes de contratos estáveis

Mitigação:

começar Inbox após Opportunity/Matching estabilizar.

## Risco 6 — ambiente funciona apenas na máquina principal

Mitigação:

teste em ambiente limpo.

---

# 75. Ordem prática completa

Sequência recomendada:

```text
01. repository/bootstrap
02. postgres/migrations
03. backend skeleton
04. frontend skeleton
05. docker compose
06. Profile
07. Company
08. Notion import dry-run
09. Notion import final
10. Acquisition contracts
11. ManualCollector
12. SourceRun/RawItem
13. Greenhouse
14. Lever
15. Ashby
16. remote source
17. normalization
18. SourceOccurrence
19. Opportunity
20. fingerprint/dedupe
21. eligibility specifications
22. deterministic scoring
23. MatchAssessment
24. explainability API
25. Ollama adapter
26. prompt/schema/cache
27. Overview
28. Opportunity Inbox
29. Opportunity Detail
30. Companies
31. Sources/Executions
32. Profile/Preferences
33. ApplicationProcess
34. Pipeline
35. logging/doctor
36. backup
37. restore-check
38. E2E
39. clean-environment validation
40. documentation review
```

---

# 76. Milestones demonstráveis

## Milestone A — Base local

```text
Compose + API + Web + DB
```

## Milestone B — Catálogo

```text
186 empresas importadas
```

## Milestone C — Primeira vaga

```text
collector → RawItem
```

## Milestone D — Opportunity canônica

```text
dedupe funcionando
```

## Milestone E — Recomendação

```text
score determinístico
```

## Milestone F — Análise semântica

```text
Ollama estruturado
```

## Milestone G — Produto utilizável

```text
Inbox + Details + Pipeline
```

## Milestone H — MVP operacional

```text
backup + restore + E2E + clean machine
```

---

# 77. Critérios globais de pronto

O MVP precisa possuir:

- [ ] migrations;
- [ ] rollback operacional documentado;
- [ ] testes do comportamento crítico;
- [ ] tratamento de erros;
- [ ] observabilidade mínima;
- [ ] nenhum secret versionado;
- [ ] loading/empty/error/retry na UI;
- [ ] documentação atualizada;
- [ ] demonstração ponta a ponta;
- [ ] restore validado;
- [ ] idempotência comprovada;
- [ ] procedência visível;
- [ ] decisões de matching reproduzíveis.

---

# 78. Demonstração final

A demo oficial deve começar de estado conhecido.

Roteiro:

```text
1. abrir dashboard vazia/controlada
2. mostrar catálogo
3. executar uma fonte
4. abrir SourceRun
5. mostrar RawItem
6. mostrar Opportunity consolidada
7. mostrar duas ocorrências quando houver dedupe
8. abrir score
9. explicar fatores
10. mostrar análise Ollama
11. iniciar candidatura
12. mudar estágio
13. reiniciar ambiente
14. provar persistência
15. executar backup
16. mostrar restore-check
```

---

# 79. Critério final de aceite

O MVP está concluído quando o sistema não é apenas “um crawler com uma tela”, mas um fluxo local coerente que:

```text
descobre
preserva
normaliza
consolida
explica
prioriza
organiza
recupera
```

o ciclo de oportunidades sem exigir intervenção técnica para cada execução normal.
