# CARD F20-03 — Conferência de aceite de F17-02, F17-04 e F17-07

- **Status:** Feito — tabela critério → evidência adicionada aos três cards; nenhum
  critério foi marcado sem evidência (os sem teste localizado ficam anotados como tal,
  não marcados). F17-02, F17-04 e F17-07 seguem "Em revisão" porque alguns critérios
  ainda não têm evidência verificável (medição no acervo real ou teste ausente).
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** A — Fechamento do que está em revisão
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-02](../../38-roadmap-ia-e-busca/fase-17/f17-02-area-da-vaga.md), [F17-04](../../38-roadmap-ia-e-busca/fase-17/f17-04-importador-propoe-todo-ats.md), [F17-07](../../38-roadmap-ia-e-busca/fase-17/f17-07-coleta-completa-e-encerradas.md)

## Resultado

Cada critério de aceite de F17-02, F17-04 e F17-07 tem evidência (commit, teste ou relatório), e os três cards saem de "Em revisão".

## Contexto

Código integrado: F17-02 (`c73cf8f`, `1287ba0`), F17-04 (`ef8345d`), F17-07 (`2818276`, `d878efc`). Testes relacionados: `tests/backend/test_role_family_integration.py`, `tests/backend/test_research_catalog_import.py`, `tests/backend/opportunities/test_run_closures.py`.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `docs/38-roadmap-ia-e-busca/fase-17/f17-02-area-da-vaga.md` | tabela critério → evidência |
| Alterar | `docs/38-roadmap-ia-e-busca/fase-17/f17-04-importador-propoe-todo-ats.md` | idem |
| Alterar | `docs/38-roadmap-ia-e-busca/fase-17/f17-07-coleta-completa-e-encerradas.md` | idem |

## Passos

1. Abrir cada card e copiar a lista de critérios de aceite.
2. Para cada critério, achar o teste que o prova (`grep` pelo nome da função ou do campo) e o commit (`git log -S`).
3. Adicionar no fim de cada card uma tabela `| Critério | Evidência |` com caminho de teste ou hash de commit.
4. Critério sem evidência: se a correção cabe em uma função, corrigir aqui com teste; senão, abrir card novo e citar no lugar da evidência.
5. Trocar o status dos três cards para `Done` quando todos os critérios tiverem evidência.

## Não fazer

- Não marcar critério sem evidência verificável.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Tabela critério → evidência nos três cards.
- [x] Nenhum critério marcado sem evidência.

## Testes

- Rodar os testes citados como evidência; todos verdes.

## Comando de verificação

```bash
docker compose -p f20-03 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/test_role_family_integration.py tests/backend/test_research_catalog_import.py tests/backend/opportunities/test_run_closures.py
docker compose -p f20-03 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-03 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
