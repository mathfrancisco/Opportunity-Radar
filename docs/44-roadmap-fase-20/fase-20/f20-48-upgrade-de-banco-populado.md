# CARD F20-48 — Upgrade de banco populado e retomada de backfill

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** F — Encerramento
- **Depende de:** F20-41, F20-12, F20-19
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-09](../../40-roadmap-varredura-produtiva/fase-18/f18-09-prova-do-fluxo-e-produtividade.md)

## Resultado

Um banco com dados anteriores à Fase 20 sobe para a versão nova sem perder histórico, e um backfill interrompido retoma sem duplicar.

## Contexto

O CI roda `alembic upgrade head` e `downgrade base` em banco vazio (job `backend-tests`). Isso não prova upgrade com dados. As migrações novas da fase são `0030` (quota), `0031` (telemetria), `0032` (sugestões).

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `tests/backend/fixtures/pre_f20_dump.sql` | dump pequeno e anonimizado na revisão `20260925_0029` |
| Criar | `tests/backend/test_upgrade_populated_integration.py` | teste |

## Passos

1. Gerar o dump: banco na revisão `20260925_0029` com perfil, 20 oportunidades, análises do Ollama (`model_id=qwen3:8b-q4_K_M`), candidaturas; anonimizar.
2. Teste: restaurar o dump, `alembic upgrade head`, conferir contagens e que análises antigas continuam legíveis com o `model_id` antigo.
3. Teste de backfill: iniciar o reprocessamento retomável do F17-06, interromper, retomar, conferir idempotência.

## Não fazer

- Não versionar dados pessoais reais no dump.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Contagens iguais antes e depois do upgrade.
- [ ] Análises antigas legíveis.
- [ ] Backfill retomado sem duplicar.

## Testes

- `tests/backend/test_upgrade_populated_integration.py`.

## Comando de verificação

```bash
docker compose -p f20-48 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/test_upgrade_populated_integration.py
docker compose -p f20-48 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-48 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Critérios marcados; teste passa com `RUN_DATABASE_INTEGRATION=1`; CI verde.
