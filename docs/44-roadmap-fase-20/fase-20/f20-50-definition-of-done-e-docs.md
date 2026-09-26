# CARD F20-50 — Definition of Done da fase e documentação final

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** F — Encerramento
- **Depende de:** F20-01 a F20-49
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); SPEC 43 §12

## Resultado

Todos os itens da Definition of Done têm evidência e os documentos refletem o que existe.

## Contexto

Último card da fase.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `docs/43-spec-llm-cloud-e-consolidacao.md` | §12 marcada com links |
| Alterar | `docs/38-roadmap-ia-e-busca.md, docs/30-runbook.md, docs/05-tecnologias.md, docs/25-docker-execucao-local.md` | estado final |
| Alterar | `READMEs das fases 16 a 20` | status final |
| Alterar | `README.md` | seção de IA: Groq, `.env`, custo |

## Passos

1. Para cada item da §12, colocar o link do PR ou teste que o prova.
2. Atualizar os documentos listados.
3. Registrar como próximos passos: provedor de embedding, busca semântica, outros provedores.

## Não fazer

- Não marcar item sem evidência.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Nenhum item da DoD sem evidência ou justificativa.

## Testes

- Suíte completa + `RUN_DATABASE_INTEGRATION=1` verde.

## Comando de verificação

```bash
docker compose -p f20-50 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend
docker compose -p f20-50 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-50 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
