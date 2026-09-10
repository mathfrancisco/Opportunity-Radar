# Tecnologias

## 1. Objetivo deste documento

Este documento define a stack oficial do Opportunity Radar, a responsabilidade de cada tecnologia, o motivo de sua escolha, onde ela pode ser usada e quais problemas ela **não** deve resolver.

A regra principal é evitar tecnologia por antecipação. O MVP usa o menor conjunto capaz de entregar o fluxo completo; a versão final adiciona componentes apenas onde o aumento de concorrência, resiliência ou observabilidade justificar.

---

## 2. Stack oficial

| Área | MVP | Versão final | Responsabilidade |
| --- | --- | --- | --- |
| Frontend | React + TypeScript + Vite + Tailwind | mesmas bases + biblioteca de componentes | dashboard e interação |
| Estado remoto | TanStack Query | TanStack Query | fetch, cache, invalidação |
| Navegação | React Router | React Router | rotas da SPA |
| Validação frontend | Zod quando necessário | Zod | validação crítica no cliente |
| API | Python 3.12 + FastAPI | mesma base | REST, composição e transporte |
| DTOs/config | Pydantic | Pydantic | contratos externos e configuração |
| ORM | SQLAlchemy 2 | SQLAlchemy 2 | persistence adapters |
| Migrações | Alembic | Alembic | evolução de schema |
| Banco | PostgreSQL 17 | PostgreSQL 17 | fonte de verdade transacional |
| Scheduler | APScheduler | Celery Beat | disparo de jobs |
| Fila | processo local | Redis + Celery | execução assíncrona e retries |
| HTTP externo | httpx | httpx | clientes async |
| Retry | tenacity | tenacity + políticas Celery | resiliência controlada |
| Parsing | selectolax / BeautifulSoup | mesmas bases | parsing permitido de HTML |
| Feeds | feedparser | feedparser | RSS/Atom |
| Similaridade | rapidfuzz | rapidfuzz | suporte lexical à deduplicação |
| IA | Ollama | Ollama com modelos por tarefa | inferência local |
| Containers | Docker Compose | Docker Compose | execução reproduzível |
| Logging | logging + Structlog | Structlog | logs estruturados |
| Métricas | mínima/custom | prometheus-client | telemetria operacional |
| Testes backend | Pytest | Pytest + Testcontainers | unit/integration |
| Testes frontend | Vitest | Vitest | unit/component |
| E2E | opcional inicial | Playwright | fluxo ponta a ponta |

---

## 3. Critérios usados na seleção

As tecnologias foram escolhidas considerando:

### 3.1 Execução local

Devem funcionar bem em uma workstation sem depender de infraestrutura gerenciada.

### 3.2 Baixo custo cognitivo

A stack deve ser suficientemente conhecida, documentada e coerente para um projeto mantido por uma pessoa.

### 3.3 Boa interoperabilidade

API, banco, workers e IA precisam se comunicar por contratos simples e testáveis.

### 3.4 Evolução incremental

O MVP não deve ficar preso a escolhas que impeçam separar scheduler, filas ou workers depois.

### 3.5 Observabilidade

A stack precisa permitir medir e diagnosticar coleta, análise, erros e jobs.

### 3.6 Reprodutibilidade

Builds, dependências e banco devem ser versionados e reproduzíveis.

---

## 4. Python 3.12

Python é a linguagem principal do backend porque combina boa produtividade com ecossistema forte para:

- APIs;
- automação;
- parsing;
- HTTP assíncrono;
- integração com LLM;
- processamento de texto;
- scripts operacionais.

### 4.1 Onde usar

- domínio;
- application layer;
- adapters;
- API;
- workers;
- scripts;
- migrations.

### 4.2 Regras

- type hints em código público/interno relevante;
- `async` somente quando existe I/O concorrente real;
- não transformar todo método em async por convenção;
- objetos de domínio independentes de Pydantic;
- lint/format definidos em tooling do projeto;
- dependências bloqueadas por lockfile.

---

## 5. FastAPI

FastAPI é a camada HTTP da aplicação.

Responsabilidades:

- registrar rotas;
- validar request;
- resolver dependências;
- autenticação futura;
- chamar handlers/application services;
- mapear erros;
- serializar response;
- gerar OpenAPI.

### 5.1 O que não pertence ao FastAPI

Não deve conter:

- regra de score;
- deduplicação;
- parser de ATS;
- SQL espalhado em route;
- chamada direta a collector dentro de controller;
- regra de transição de candidatura.

### 5.2 Organização sugerida

```text
presentation/http/
├── routes.py
├── schemas.py
├── dependencies.py
├── error_handlers.py
└── pagination.py
```

---

## 6. Pydantic

Pydantic é usado para:

- request schemas;
- response schemas;
- configuração de ambiente;
- validação de contratos externos quando conveniente;
- parsing de respostas estruturadas do Ollama em camada de adapter/application.

Não deve substituir:

- entities;
- value objects;
- aggregates.

A entidade de domínio deve continuar válida mesmo que a aplicação deixe de usar FastAPI/Pydantic.

---

## 7. SQLAlchemy 2

SQLAlchemy implementa persistence adapters.

### 7.1 Responsabilidades

- mapping relacional;
- queries transacionais;
- repositories;
- Unit of Work;
- locking;
- paginação de consultas quando apropriado.

### 7.2 Regras

- ORM model não sai da infrastructure;
- repository converte ORM ↔ domínio;
- módulo não importa ORM model de outro bounded context;
- query models específicos podem usar SQL direto/SQLAlchemy Core quando isso simplificar leitura;
- N+1 precisa ser evitado nas telas principais.

---

## 8. Alembic

Alembic é a única forma autorizada de modificar schemas persistentes.

### 8.1 Convenções

- migration aplicada nunca é editada;
- migration deve ser revisada manualmente;
- downgrade é fornecido quando seguro;
- mudança destrutiva exige backup/instrução explícita;
- migrations grandes usam `expand → migrate → contract`;
- schema de cada contexto continua reconhecível pela organização das migrations.

### 8.2 Startup

A aplicação não deve permitir que múltiplos serviços executem migrations concorrentes sem coordenação.

---

## 9. PostgreSQL 17

PostgreSQL é a fonte de verdade do sistema.

Foi escolhido por oferecer no mesmo banco:

- ACID;
- foreign keys;
- unique constraints;
- check constraints;
- JSONB;
- full text features básicas;
- índices parciais;
- extensões;
- views;
- materialized views;
- locking;
- transações maduras.

### 9.1 Schemas

```text
profile
company_radar
acquisition
opportunities
matching
crm
outreach
proposals
interviews
automation
platform
```

### 9.2 Tipos recomendados

- `uuid` para IDs públicos;
- `timestamptz` para timestamps;
- `numeric` para dinheiro;
- `jsonb` para payload externo/metadado realmente variável;
- `citext` quando case-insensitive é semanticamente necessário;
- `text`/`varchar + check` para estados evolutivos.

### 9.3 JSONB

Uso adequado:

- payload bruto;
- metadata externa;
- explicação estruturada variável;
- configuração específica de adapter.

Uso inadequado:

- colocar entidades inteiras em JSON para evitar modelagem relacional;
- esconder campos que precisam de índice ou constraint.

---

## 10. Extensões PostgreSQL

### `pg_trgm`

Pode auxiliar:

- aliases de empresas;
- similaridade de títulos;
- busca textual tolerante.

### `pgvector`

Não entra automaticamente. Só deve ser ativado se um caso mensurável demonstrar que embeddings melhoram matching, deduplicação ou recuperação semântica.

A arquitetura não depende de vector database dedicado.

---

## 11. React

React implementa a dashboard local.

### 11.1 Organização por feature

Exemplo:

```text
src/features/
├── opportunities/
├── companies/
├── sources/
├── profile/
├── pipeline/
└── operations/
```

Cada feature concentra:

- componentes;
- hooks;
- query keys;
- schemas locais;
- transformations de apresentação;
- testes.

### 11.2 Regra de estado

Separar:

- **server state** → TanStack Query;
- **UI state** → estado local/context pequeno;
- **form state** → biblioteca/form hooks se necessário.

Não duplicar lista de oportunidades inteira em store global apenas para “ter estado centralizado”.

---

## 12. TypeScript

TypeScript é obrigatório no frontend para:

- reduzir erros de contrato;
- melhorar refatoração;
- documentar estruturas;
- tipar componentes e hooks.

Tipos gerados a partir de OpenAPI podem ser considerados na fase de implementação para reduzir divergência entre backend e frontend.

---

## 13. Vite

Vite fornece:

- dev server rápido;
- build simples;
- bom suporte a React/TypeScript;
- baixa complexidade para uma SPA local.

Não há necessidade inicial de Next.js, SSR ou Server Components porque o sistema é uma dashboard autenticada/local, não um produto público focado em SEO.

---

## 14. Tailwind

Tailwind é usado como camada utilitária de estilo.

Regras recomendadas:

- tokens semânticos para spacing/tipografia;
- componentes reutilizáveis para padrões recorrentes;
- evitar classes gigantes repetidas;
- separar variantes de componentes;
- não misturar regra de negócio com decisão visual.

Na versão final pode ser adicionada uma biblioteca de componentes, mantendo Tailwind como base.

---

## 15. TanStack Query

É a ferramenta oficial para server state.

Responsabilidades:

- fetch;
- cache;
- invalidação;
- retry de request de leitura;
- estados loading/error;
- paginação/infinite query quando necessário.

Cada domínio visual deve definir query keys consistentes.

Exemplo conceitual:

```text
['opportunities', filters]
['opportunity', opportunityId]
['companies', filters]
['source-runs', sourceId]
```

---

## 16. React Router

Responsável apenas pela navegação.

Rotas previstas:

```text
/
/opportunities
/opportunities/:id
/companies
/companies/:id
/sources
/profile
/pipeline
/operations
```

---

## 17. Zod

Zod pode validar:

- formulários;
- config de frontend;
- payloads críticos quando a confiança no contrato exige runtime validation.

Não é necessário validar novamente todos os responses indiscriminadamente se contratos gerados e testes já cobrirem o fluxo.

---

## 18. APScheduler no MVP

APScheduler é escolhido porque reduz dependências operacionais.

Responsabilidades:

- agendar coleta;
- disparar retries locais;
- executar manutenção simples.

Limitações aceitas:

- processo único;
- menos isolamento;
- menor capacidade de prioridade;
- recuperação de jobs mais simples.

Quando essas limitações forem observáveis, migra-se para Celery Beat/Celery.

---

## 19. Redis na versão final

Redis atua como infraestrutura efêmera.

Usos permitidos:

- broker Celery;
- lock curto;
- cache temporário;
- rate limit;
- coordenação.

Uso proibido:

- guardar estado de candidatura como única cópia;
- guardar score como única cópia;
- manter histórico de domínio apenas em Redis.

---

## 20. Celery

Celery entra quando o worker único deixa de ser suficiente.

### 20.1 Motivações

- tarefas independentes;
- retries persistentes;
- roteamento;
- prioridades;
- concorrência;
- workers especializados;
- isolamento de análise.

### 20.2 Tasks

Tasks devem ser finas.

Preferência:

```text
Celery task
→ resolve container/dependencies
→ chama application handler
→ retorna resultado operacional
```

Evitar colocar regra de domínio dentro de task function.

---

## 21. httpx

Cliente HTTP oficial para adapters externos.

Configuração comum deve cobrir:

- timeout de conexão;
- timeout de leitura;
- limite de conexões;
- headers padrão;
- User-Agent quando apropriado;
- redirects controlados;
- tracing/logging.

Clientes por fonte podem especializar política sem duplicar boilerplate.

---

## 22. tenacity

Usada para retry explícito em chamadas de infraestrutura que não estão sob Celery.

Retry deve depender da classe do erro, não de `except Exception` genérico.

Exemplos retryable:

- timeout;
- connection reset;
- HTTP 429;
- HTTP 502/503/504.

Exemplos normalmente não retryable:

- 400;
- 401 por credencial inválida;
- parser incompatível;
- regra de domínio inválida.

---

## 23. Parsing de HTML

`selectolax` ou `BeautifulSoup` podem ser usados apenas em páginas onde o acesso e o parsing estejam de acordo com a estratégia de fontes.

### Escolha prática

- `selectolax`: rápido e simples para HTML;
- `BeautifulSoup`: ecossistema familiar e tolerante.

O adapter deve esconder a biblioteca do domínio.

---

## 24. feedparser

Usado para RSS/Atom.

O adapter converte feed entries em `CollectedItem` e preserva dados relevantes do item original.

---

## 25. rapidfuzz

Ferramenta auxiliar, não autoridade final de deduplicação.

Pode calcular:

- similaridade de nomes;
- similaridade de títulos;
- comparação de aliases.

Uma alta similaridade lexical isolada não deve automaticamente fundir oportunidades.

---

## 26. Ollama

Ollama executa modelos localmente e expõe interface HTTP para o sistema.

### 26.1 Responsabilidades

- classificação semântica;
- extração estruturada;
- análise de gaps;
- resumo;
- preparação textual futura.

### 26.2 Não responsabilidades

- persistência;
- score determinístico;
- regra de elegibilidade;
- controle de candidatura.

### 26.3 Configuração

A escolha do modelo deve vir de variável/configuração:

```text
OLLAMA_BASE_URL
OLLAMA_MODEL_ANALYSIS
OLLAMA_MODEL_OUTREACH
OLLAMA_MODEL_INTERVIEW
```

O código não deve espalhar nomes de modelos em handlers.

---

## 27. Estratégia de modelos

### MVP

Começar com um modelo capaz de gerar JSON confiável dentro do hardware disponível.

### Versão final

Modelos podem ser especializados por tarefa:

- análise de oportunidade;
- outreach;
- proposta;
- entrevista.

Isso permite equilibrar:

- qualidade;
- VRAM/RAM;
- latência;
- contexto;
- throughput.

---

## 28. Saída estruturada da IA

Toda operação que altera dados estruturados exige schema.

Pipeline:

```text
prompt
→ resposta do modelo
→ parse JSON
→ validação
→ normalização
→ persistência
```

A resposta bruta pode ser preservada para diagnóstico, porém somente o objeto validado entra no fluxo principal.

---

## 29. Docker

Docker padroniza o runtime.

Cada serviço deve possuir:

- imagem reproduzível;
- usuário não-root quando aplicável;
- healthcheck;
- volumes explícitos;
- variáveis documentadas;
- logs em stdout/stderr;
- dependências declaradas por readiness real, não apenas ordem de start.

---

## 30. Docker Compose

Compose é o orquestrador oficial porque o projeto é local-first e single-machine.

O Compose deve controlar:

### MVP

```text
frontend
api
worker
postgres
ollama
```

### Final

```text
frontend
api
scheduler
worker-collector
worker-analysis
worker-maintenance
postgres
redis
ollama
ollama-init
backup
```

---

## 31. Structlog

Logs estruturados devem permitir filtros por campos.

Exemplo conceitual:

```json
{
  "event": "source_run_finished",
  "source_run_id": "...",
  "source_type": "greenhouse",
  "items_collected": 42,
  "items_new": 7,
  "duration_ms": 1832
}
```

Evitar depender apenas de mensagens como:

```text
"deu erro na coleta"
```

---

## 32. Prometheus client

Na versão final, métricas instrumentam comportamento operacional.

Categorias:

- counters;
- gauges;
- histograms.

Exemplos:

```text
source_run_duration_seconds
collector_requests_total
collector_errors_total
analysis_duration_seconds
analysis_queue_depth
outbox_pending_events
```

A stack não exige instalar uma plataforma de observabilidade completa desde o MVP.

---

## 33. Pytest

Framework principal de teste do backend.

Estrutura:

```text
tests/
├── unit/
├── integration/
├── contract/
└── e2e/
```

Fixtures devem representar dados estáveis e pequenos.

---

## 34. Testcontainers

Entra na versão final — ou antes, se conveniente — para validar integração contra dependências reais, especialmente PostgreSQL.

Benefícios:

- reduz diferença entre mock e comportamento real;
- testa constraints;
- testa migrations;
- testa SQL.

Não é substituto de unit tests rápidos.

---

## 35. Vitest

Usado no frontend para:

- utilitários;
- hooks;
- componentes;
- regras de apresentação.

---

## 36. Playwright

Usado para provar fluxos completos.

Cenários prioritários:

- abrir inbox;
- filtrar;
- abrir oportunidade;
- ver explicação;
- iniciar candidatura;
- mover stage;
- visualizar source failure.

---

## 37. Ferramentas deliberadamente adiadas

### Kubernetes

Não há cluster nem múltiplas máquinas que justifiquem sua complexidade.

### Kafka

O throughput esperado não exige event streaming distribuído. Outbox + Redis/Celery é suficiente.

### Elasticsearch/OpenSearch

PostgreSQL cobre filtros, busca textual básica e volume esperado.

### Vector database dedicado

Só entra com evidência de necessidade.

### GraphQL

REST atende os fluxos e mantém contratos mais simples.

### Next.js

A dashboard não precisa SSR/SEO e o backend já está separado.

### Microsserviços

Fronteiras lógicas primeiro; distribuição física apenas sob pressão real.

---

## 38. Gerenciamento de dependências

### Python

O projeto deve possuir arquivo declarativo e lock consistente com a ferramenta escolhida.

Regras:

- versões explícitas;
- atualizações em lotes pequenos;
- separar dependências de runtime/dev quando útil;
- verificar breaking changes antes de atualizar major/minor sensível.

### Node

Manter lockfile versionado e usar uma ferramenta de pacote única no repositório.

---

## 39. Política de versões

### Imagens Docker

Evitar tags vagas como `latest` para componentes de infraestrutura críticos.

### Bibliotecas

Dependências de produção precisam de versão resolvida no lockfile.

### Atualização

Fluxo recomendado:

```text
branch de atualização
→ atualizar dependência
→ executar testes
→ subir compose limpo
→ executar migrations
→ smoke tests
→ merge
```

---

## 40. Configuração por ambiente

Variáveis típicas:

```text
APP_ENV
LOG_LEVEL
DATABASE_URL
FRONTEND_ORIGIN
COLLECTION_TIMEZONE
OLLAMA_BASE_URL
OLLAMA_MODEL_ANALYSIS
REDIS_URL
BACKUP_RETENTION_DAYS
```

Regras:

- `.env.example` documenta todas as chaves;
- `.env` real não é versionado;
- configuração é validada no startup;
- erro de configuração obrigatória deve falhar cedo;
- valores secretos não aparecem em logs.

---

## 41. Escolhas por fase

### MVP

Priorizar simplicidade:

```text
React + Vite
FastAPI
SQLAlchemy + Alembic
PostgreSQL
APScheduler
Ollama
Docker Compose
Pytest/Vitest
```

### Evolução

Adicionar conforme necessidade:

```text
Redis
Celery
Celery Beat
Prometheus metrics
Testcontainers
Playwright
component library
```

---

## 42. Matriz tecnologia × responsabilidade

| Necessidade | Tecnologia principal | Fallback/observação |
| --- | --- | --- |
| REST | FastAPI | contratos OpenAPI |
| validação HTTP | Pydantic | domínio separado |
| persistência | PostgreSQL | fonte de verdade |
| ORM | SQLAlchemy | Core/SQL em queries específicas |
| migration | Alembic | nenhuma alteração manual |
| HTTP externo | httpx | adapters específicos |
| scheduler MVP | APScheduler | migra para Beat |
| tasks finais | Celery | jobs idempotentes |
| broker | Redis | não é banco de negócio |
| IA | Ollama | degradação permitida |
| UI | React | SPA local |
| server cache | TanStack Query | sem store duplicada |
| container | Docker Compose | single-host |
| observabilidade | Structlog | métricas depois |

---

## 43. Regras arquiteturais relacionadas à stack

1. FastAPI não contém regra de domínio.
2. Pydantic não substitui entidades.
3. SQLAlchemy não vaza para Domain.
4. Alembic é obrigatório para schema persistente.
5. Redis não é fonte de verdade.
6. Celery task chama caso de uso, não repository concreto diretamente.
7. Ollama é adapter substituível.
8. React não reimplementa score no cliente.
9. TanStack Query gerencia server state.
10. Docker Compose continua suficiente enquanto a execução for single-host.

---

## 44. Critério para adicionar nova tecnologia

Antes de adicionar biblioteca ou infraestrutura, responder:

1. Qual problema mensurável ela resolve?
2. Esse problema já existe no projeto?
3. A stack atual realmente não consegue resolvê-lo de forma aceitável?
4. Qual custo operacional adicional ela cria?
5. Como será testada?
6. Como será removida/substituída se necessário?
7. Ela respeita as fronteiras de domínio?

Se a resposta depender apenas de “pode ser útil no futuro”, a tecnologia deve permanecer adiada.
