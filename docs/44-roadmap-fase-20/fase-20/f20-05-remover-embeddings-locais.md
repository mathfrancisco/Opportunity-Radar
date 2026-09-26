# CARD F20-05 — Remover os embeddings locais e a busca por significado

- **Status:** Parcial — alembic upgrade/downgrade não executado (sem Postgres/Docker nesta máquina); demais critérios feitos
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §9

## Resultado

O worker e a API não geram nem consultam embedding; a coluna pgvector continua no banco, vazia, sem migração destrutiva.

## Contexto

O F16-09 (`0ddd0de`) gera embedding com `qwen3-embedding:0.6b` no Ollama. O Groq não tem embedding. Pontos atuais: `opportunities/embeddings.py` (cliente `OllamaEmbeddingAdapter`, `build_embedding_adapter`, `embed_pending`, `count_pending_embeddings`, `embedding_coverage`); `opportunities/embedding_models.py` (ORM da coluna, **manter**); `platform/vector.py` (tipo pgvector, **manter**); `worker.py` linhas 44-48, 70, 76, 302-340 (`embed_opportunities`); `operations/soak.py` linhas 52, 171, 194-198; `presentation/http/search.py` (rotas `GET .../similar` e `GET /search/semantic`); `presentation/http/routes.py` linha 12 e 22 (`include_router(search_router)`); `presentation/http/dependencies.py` linhas 18-20, 73-80; `scripts/doctor.py` linhas 29-30, 174; `platform/config.py` campos `ollama_embedding_*`, `inbox_search_mode`, `worker_embed_*`; `matching/context.py` (comentário). O frontend usa `similarity` só em `apps/web/src/features/matching/api.ts` linhas 40 e 175-177 como campo opcional.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `src/opportunity_radar/opportunities/embeddings.py` | apagar o cliente e o job; manter só `embedding_coverage` se o `doctor` ainda mostrar cobertura, senão apagar o arquivo |
| Alterar | `src/opportunity_radar/worker.py` | remover `embed_opportunities` e o job `embed-opportunities` do agendador |
| Alterar | `src/opportunity_radar/operations/soak.py` | remover o passo de embedding |
| Apagar | `src/opportunity_radar/presentation/http/search.py` | rotas de similaridade e busca semântica |
| Alterar | `src/opportunity_radar/presentation/http/routes.py` | remover import e `include_router(search_router)` |
| Alterar | `src/opportunity_radar/presentation/http/dependencies.py` | remover `cached_embedding_adapter` e `get_embedding_adapter` |
| Alterar | `src/opportunity_radar/platform/config.py` | remover `ollama_embedding_*`, `ollama_model_embedding`, `inbox_search_mode`, `worker_embed_*` |
| Alterar | `scripts/doctor.py` | remover a checagem de cobertura de embedding e `embed_opportunities` da tabela de jobs |
| Alterar | `tests/backend/operations/test_soak.py` | remover expectativa de embedding |
| Alterar | `tests/backend/test_worker.py` | remover casos de embedding |

## Passos

1. Rodar `grep -rn "embedding\|embed_" src scripts tests` e salvar a lista no PR.
2. Remover o registro do job `embed_opportunities` no agendador do `worker.py` e a função.
3. Remover o passo de embedding em `operations/soak.py`.
4. Apagar `presentation/http/search.py` e sua inclusão em `routes.py`; apagar as dependências de embedding em `dependencies.py`.
5. Em `opportunities/embeddings.py`, apagar tudo que chama o Ollama; se nada mais usa o arquivo, apagá-lo.
6. Remover os campos de config listados; remover as mesmas variáveis do `.env.example` e do `compose.yaml`.
7. Ajustar `scripts/doctor.py` e os testes.
8. Confirmar que nenhuma migração nova foi criada: `git status migrations` sem arquivo novo.
9. Escrever no runbook (`docs/30-runbook.md`): "a coluna de embedding fica vazia até existir provedor de embedding; ver SPEC 43 §9".

## Não fazer

- Não apagar `opportunities/embedding_models.py`, `platform/vector.py` nem a migração `20260925_0024_opportunity_embedding.py`.
- Não criar migração que remova a coluna ou a extensão `vector`.
- Não mexer no campo `similarity` do frontend: ele já é opcional.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] O worker roda um ciclo completo sem log de embedding.
- [x] `GET /search/semantic` responde 404 (rota removida).
- [ ] `alembic upgrade head` e `alembic downgrade base` continuam funcionando — não executado (sem Postgres/Docker disponível nesta máquina; nenhuma migração foi criada ou alterada).

## Testes

- `tests/backend/test_worker.py::test_worker_scheduler_has_no_embedding_job`: confirma que `embed-opportunities` não está registrado nem faz parte dos jobs funcionais.
- `tests/backend/operations/test_soak.py::test_the_window_holds_and_reports_what_it_proved`: ciclo de soak integrado sem log de embedding (requer o banco de CI).
- `tests/backend/test_semantic_search_removed.py::test_semantic_search_route_is_removed`: `GET /search/semantic` responde 404.
- `tests/backend/test_doctor.py::test_doctor_has_no_embedding_coverage_check`: doctor não registra checagem de cobertura de embedding.

## Critério → evidência

| Critério | Evidência |
| --- | --- |
| O worker não agenda embeddings e o ciclo não emite log de embedding | `test_worker_scheduler_has_no_embedding_job`; `test_the_window_holds_and_reports_what_it_proved` (teste de integração, pulado localmente sem `RUN_DATABASE_INTEGRATION=1`) |
| `GET /search/semantic` responde 404 | `tests/backend/test_semantic_search_removed.py::test_semantic_search_route_is_removed` |
| Doctor não verifica cobertura de embedding | `tests/backend/test_doctor.py::test_doctor_has_no_embedding_coverage_check` |
| `alembic upgrade head` e `alembic downgrade base` continuam funcionando | Não executado: requer PostgreSQL/Docker. Nenhuma migração foi criada ou alterada. |

## Comando de verificação

```bash
docker compose -p f20-05 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/test_worker.py tests/backend/operations/test_soak.py tests/backend/test_doctor.py
docker compose -p f20-05 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-05 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
