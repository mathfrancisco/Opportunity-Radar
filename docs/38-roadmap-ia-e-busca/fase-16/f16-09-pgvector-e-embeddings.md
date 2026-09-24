# CARD F16-09 — pgvector e embeddings das vagas

- **Status:** Backlog
- **Fase:** 16 — Camada local de IA
- **Depende de:** F16-01
- **Bloqueia:** F16-10, F16-11, F17-08
- **Origem:** [SPEC da camada de IA](../../36-spec-ollama.md), §7.1, §7.2

## Resultado

Toda oportunidade não rejeitada tem um vetor de 1 024 dimensões do `qwen3-embedding:0.6b`,
guardado no Postgres com pgvector e mantido atual pelo worker.

## Contexto

O operador decidiu construir a infraestrutura vetorial agora (SPEC §3.3, §7.1). O banco
roda em `postgres:17.2-alpine`, sem pgvector. A imagem oficial `pgvector/pgvector` é
Debian: trocar a base sobre o volume existente muda a ordenação de texto (musl → glibc)
sob índices já construídos, o que corrompe índices sem erro visível.

## Escopo

- **Imagem do Postgres** (`docker/postgres/Dockerfile`):

  ```dockerfile
  FROM postgres:17.2-alpine
  ARG PGVECTOR_VERSION=0.8.6
  RUN apk add --no-cache --virtual .build-deps git build-base \
   && git clone --branch v${PGVECTOR_VERSION} --depth 1 \
        https://github.com/pgvector/pgvector.git /tmp/pgvector \
   && make -C /tmp/pgvector OPTFLAGS="" with_llvm=no \
   && make -C /tmp/pgvector install with_llvm=no \
   && rm -rf /tmp/pgvector && apk del .build-deps
  ```

  `compose.yaml` passa a construir essa imagem no serviço `postgres`.
- **CI:** o serviço de Postgres do job de backend usa `pgvector/pgvector:0.8.6-pg17` (banco
  sempre novo, sem volume a proteger). O job de compose constrói a imagem do projeto.
- **Migração:** `CREATE EXTENSION IF NOT EXISTS vector`; tabela
  `opportunities.opportunity_embedding (opportunity_id PK/FK cascade, content_version,
  model, text_hash, embedding vector(1024), created_at)`; índice HNSW
  `vector_cosine_ops`. A coluna e o índice vão por SQL, porque o Alembic não conhece o tipo.
- **Tipo SQLAlchemy próprio** (`platform/vector.py`), sem o pacote `pgvector`: escreve
  `[x,y,…]`, lê o mesmo formato, e sempre com `CAST(… AS vector(1024))` no bind.
- **Texto que vira vetor** (`opportunities/embeddings.py`): título, empresa, local, modo de
  trabalho, senioridade, skills e descrição limpa (limpador do F16-05, ou a versão mínima
  deste card se ele ainda não existir), limitado a 6 000 caracteres.
- **Adaptador de embedding:** `POST /api/embed` com `{"model", "input": [textos],
  "keep_alive"}`, síncrono (o job do worker é síncrono), lote inteiro numa chamada; confere
  que cada vetor tem 1 024 posições.
- **Job `embed_opportunities`:** a cada 120 s, lote de `WORKER_EMBED_BATCH_SIZE` (32)
  oportunidades sem vetor, com `content_version` defasada ou com `model` diferente do
  configurado. Chave de desligar `WORKER_EMBED_ENABLED`. Entra em `FUNCTIONAL_JOB_IDS`.
- **Configuração:** `OLLAMA_EMBEDDING_ENABLED`, `OLLAMA_MODEL_EMBEDDING`,
  `OLLAMA_EMBEDDING_DIMENSIONS` (1024, documentado como amarrado à coluna),
  `OLLAMA_EMBEDDING_TIMEOUT_SECONDS`.
- **Ollama falso:** `/api/embed` devolve vetores determinísticos de 1 024 posições
  (derivados do hash do texto, normalizados).

## Fora de escopo

- Endpoints e tela de vagas parecidas e de busca (F16-10).
- Uso dos vetores na análise (F16-11).

## Notas de implementação

- `FUNCTIONAL_JOB_IDS` ganha `embed_opportunities`. Isso quebra de propósito três lugares
  que precisam ser atualizados no mesmo PR: `tests/backend/test_worker.py` (lista de
  chaves de desligar), a asserção de igualdade exata do passo "Verify the kill switches
  reach the worker" do E2E, e o `up --force-recreate worker` do mesmo passo, que precisa
  de `WORKER_EMBED_ENABLED=false`.
- `CREATE EXTENSION` exige superusuário; o usuário do compose e o do CI são.
- `/api/embed` devolve vetores já normalizados (L2), então cosseno e produto interno
  ordenam igual; o índice usa cosseno pela clareza.
- O `qwen3-embedding` usa instrução só na consulta (F16-10), não nos documentos.
- Downgrade da migração remove tabela e extensão; nada se perde que o job não refaça.

## Critérios de aceite

- [ ] O Postgres do compose tem pgvector 0.8.6, sem trocar a base alpine.
- [ ] A migração cria extensão, tabela e índice HNSW, e desce sem erro.
- [ ] O job preenche vetores para vagas novas e refaz os de vagas alteradas ou de modelo
      diferente.
- [ ] Vetor com dimensão errada é recusado com erro classificado, sem gravar.
- [ ] `WORKER_EMBED_ENABLED=false` remove só o job de embedding.
- [ ] O E2E confere, depois do ciclo autônomo, que as oportunidades têm vetor.

## Verificação

- **CI:** migração de ida e volta no job de backend (imagem pgvector); testes do tipo
  `Vector` (ida e volta de valores); teste de integração do job com adaptador falso;
  `test_worker.py` atualizado; E2E com contagem de linhas em
  `opportunities.opportunity_embedding` via `psql`, dentro do `wait_for` do ciclo
  autônomo.
- **Máquina de referência:** tempo do lote de 32 na GPU, registrado no PR.

## Arquivos prováveis

- `docker/postgres/Dockerfile` (novo), `compose.yaml`, `.github/workflows/pipeline.yml`
- `migrations/versions/*_opportunity_embedding.py`
- `src/opportunity_radar/platform/vector.py` (novo), `platform/config.py`
- `src/opportunity_radar/opportunities/models.py`, `opportunities/embeddings.py` (novo)
- `src/opportunity_radar/worker.py`, `tests/backend/test_worker.py`
- `tests/e2e/fake_ollama.py`
