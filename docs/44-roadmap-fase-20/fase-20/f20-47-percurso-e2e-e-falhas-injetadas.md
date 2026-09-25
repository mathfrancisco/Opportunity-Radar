# CARD F20-47 — Percurso E2E no navegador com falhas injetadas

- **Status:** Backlog
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** F — Encerramento
- **Depende de:** F20-17, F20-39, F20-40, F20-25
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F18-09](../../40-roadmap-varredura-produtiva/fase-18/f18-09-prova-do-fluxo-e-produtividade.md)

## Resultado

O ciclo perfil → preferência → coleta → busca → análise → candidatura roda no navegador do CI com falhas injetadas, sem perda nem encerramento indevido.

## Contexto

O job `e2e` do `.github/workflows/pipeline.yml` sobe `api`, `worker` e `frontend` com `compose.ci.yaml` e hoje só verifica health e modo degradado. `tests/e2e/fake_job_board.py` e `fake_groq.py` (F20-17) são os servidores falsos.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Criar | `tests/e2e/browser/` | teste Playwright do percurso |
| Alterar | `tests/e2e/fake_groq.py` | modo de falha por variável (`FAKE_GROQ_MODE=429|500|invalid|ok`) |
| Alterar | `tests/e2e/fake_job_board.py` | paginação parcial e 304 por variável |
| Alterar | `.github/workflows/pipeline.yml` | passo do navegador e upload de evidências |

## Passos

1. Escrever o percurso feliz no navegador: preencher perfil, editar preferência, disparar coleta, buscar, abrir vaga, analisar, criar candidatura.
2. Adicionar cenários: paginação parcial, 304, Groq 429, Groq 500, Groq inválido, restart do `worker` no meio da coleta.
3. Em cada cenário, verificar: nenhuma vaga duplicada, nenhuma vaga ativa marcada como encerrada, Inbox mostra a vaga sem comentário quando a IA falha.
4. Anexar screenshots e trace como artefato do CI.

## Não fazer

- Não chamar Groq nem boards reais.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Percurso completo passa sem terminal.
- [ ] Todos os cenários de falha passam.
- [ ] Evidências anexadas no CI.

## Testes

- Os próprios testes de navegador.

## Pronto quando

Job `e2e` verde no CI com os cenários e artefatos.
