# CARD F20-04 — Remover o Ollama do compose, da config e do worker

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** B — IA cloud no Groq
- **Depende de:** F20-17
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §2.2, §3

## Resultado

Com o adapter Groq funcionando (F20-17), nenhum serviço, variável ou código de execução do radar depende de Ollama ou GPU.

## Contexto

Este card roda **depois** do F20-17: o `GroqAnalysisAdapter` é escrito movendo a lógica de `prepare` de `matching/ollama.py`, então o arquivo antigo só pode sair quando o novo estiver pronto. Pontos atuais: `compose.yaml` linhas 7, 79-125, 170, 206 (serviços `ollama`, `ollama-init`, volume `ollama_models`, `OLLAMA_BASE_URL`); `compose.cpu.yaml` (override inteiro de Ollama em CPU); `compose.ci.yaml` (serviço `ollama` com `fake_ollama.py`); `platform/config.py` (campos `ollama_*`); `worker.py` (`GpuAdmission` linhas 73-131, `warm_up_models` linha 203, uso de `admission.hold()` em `analyze_pending`).

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `compose.yaml` | remover `ollama`, `ollama-init`, volume `ollama_models`, `OLLAMA_*` e `depends_on: ollama`; adicionar `GROQ_API_KEY: ${GROQ_API_KEY:-}` e `AI_*` no ambiente de `api` e `worker` |
| Apagar | `compose.cpu.yaml` | só existia para Ollama em CPU |
| Alterar | `compose.ci.yaml` | trocar o serviço `ollama` pelo fake Groq do F20-17 (`GROQ_BASE_URL` apontando para ele) |
| Alterar | `Makefile` | remover `up-cpu` |
| Apagar | `src/opportunity_radar/matching/ollama.py` | substituído por `matching/groq.py` |
| Alterar | `src/opportunity_radar/platform/config.py` | remover todos os campos `ollama_*` de análise |
| Alterar | `src/opportunity_radar/worker.py` | remover `GpuAdmission`, `GPU_ADMISSION`, `warm_up_models`, `_log_warm_up` e os `with admission.hold()` |
| Apagar | `tests/backend/matching/test_ollama_adapter.py` | coberto por `test_groq_adapter.py` |
| Alterar | `tests/backend/test_worker.py` | remover casos de admissão de GPU e aquecimento |
| Alterar | `.env.example` | remover `OLLAMA_*` |

## Passos

1. Confirmar que `pytest -q tests/backend/matching/test_groq_adapter.py` passa (F20-17 concluído).
2. Em `compose.yaml`, apagar os serviços `ollama` e `ollama-init`, o volume `ollama_models` e toda variável `OLLAMA_*`; remover `ollama` de `depends_on`.
3. Adicionar em `api` e `worker`: `GROQ_API_KEY: ${GROQ_API_KEY:-}`, `AI_ENABLED: ${AI_ENABLED:-false}` e as demais `AI_*`/`GROQ_*` da SPEC §5 com `${VAR:-padrão}`.
4. Apagar `compose.cpu.yaml` e o alvo `up-cpu` do `Makefile`.
5. Em `compose.ci.yaml`, substituir o serviço `ollama` pelo serviço `groq` que roda `tests/e2e/fake_groq.py` (criado no F20-17) e setar `GROQ_BASE_URL=http://groq:8080/openai/v1`, `GROQ_API_KEY=ci-fake`, `AI_ENABLED=true` em `api` e `worker`.
6. Em `platform/config.py`, apagar os campos `ollama_base_url` até `ollama_analysis_prompt` (os de embedding saem no F20-05).
7. Em `worker.py`, apagar `GpuAdmission` e `warm_up_models`; em `analyze_pending`, remover o parâmetro `admission` e o `with admission.hold()`, mantendo a chamada ao adapter.
8. Apagar `matching/ollama.py` e `tests/backend/matching/test_ollama_adapter.py`.
9. Rodar `grep -rn "ollama" src/opportunity_radar/worker.py src/opportunity_radar/platform/config.py compose*.yaml Makefile` e zerar o resultado.
10. Rodar a suíte e o `docker compose -f compose.yaml -f compose.ci.yaml config --quiet`.

## Não fazer

- Não apagar `matching/analysis.py`, `matching/prompts.py`, `matching/text.py` nem `prompts/`: o Groq usa.
- Não mexer em embeddings (F20-05) nem em health/doctor/scripts (F20-06).
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] `docker compose up` sobe sem GPU e sem baixar modelo.
- [ ] `docker compose -f compose.yaml -f compose.ci.yaml config --quiet` passa.
- [ ] Sem `GROQ_API_KEY`, coleta, normalização, avaliação e Inbox funcionam e a análise aparece como bloqueada por configuração.

## Testes

- `tests/backend/test_worker.py`: `analyze_pending` chama o adapter sem admissão de GPU.
- Suíte do backend inteira verde.

## Comando de verificação

```bash
docker compose -p f20-04 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/test_worker.py tests/backend/matching
docker compose -p f20-04 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-04 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
