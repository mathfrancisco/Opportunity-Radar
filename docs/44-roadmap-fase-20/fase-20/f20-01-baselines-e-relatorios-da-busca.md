# CARD F20-01 — Baselines e relatórios da busca

- **Status:** Parcial — requer `make up` com o acervo real e marcação manual de relevância
  na Inbox (passo 2) e a máquina de referência para `make eval-search`; não executável
  neste ambiente (sem Docker, sem acervo real). Nenhum código alterado, como pede este
  card.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** A — Fechamento do que está em revisão
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-01](../../38-roadmap-ia-e-busca/fase-17/f17-01-relevancia-e-relatorios.md), [F17-03](../../38-roadmap-ia-e-busca/fase-17/f17-03-busca-full-text.md)

## Resultado

A baseline de relevância do F17-01 e o relatório do `eval_search.py` do F17-03 existem, medidos no acervo real e versionados.

## Contexto

O código do F17-01 (`f2fca7a`) e do F17-03 (`2e5fa5c`, `48bf252`) está integrado. Os dois cards estão "Em revisão" só porque faltam as medições na máquina de referência. `docs/pesquisas/baseline-f17-01.md` já existe e está incompleto.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `docs/pesquisas/baseline-f17-01.md` | completar com a baseline real |
| Criar | `docs/pesquisas/eval-search-f17-03.md` | relatório do `eval_search.py` |
| Alterar | `docs/38-roadmap-ia-e-busca/fase-17/f17-01-relevancia-e-relatorios.md` | status e link |
| Alterar | `docs/38-roadmap-ia-e-busca/fase-17/f17-03-busca-full-text.md` | status e link |

## Passos

1. Subir o ambiente com `make up` e confirmar o acervo real carregado.
2. Na Inbox, marcar relevância numa amostra de pelo menos 100 vagas, como o F17-01 descreve.
3. Rodar o relatório de cobertura e precisão do F17-01 e colar a saída em `baseline-f17-01.md`, com data, tamanho da amostra e versão das regras.
4. Rodar `make eval-search` e salvar a saída em `eval-search-f17-03.md` (precisão, cobertura, latência).
5. Nos dois cards antigos, trocar o status para `Done` e adicionar o link para o relatório.
6. Se algum número ficou inconclusivo (amostra pequena), escrever isso no relatório em vez de omitir.

## Não fazer

- Não alterar código; este card só mede e documenta.
- Não inventar números: todo valor vem de uma saída de comando colada no relatório.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [ ] Os dois relatórios estão versionados e citados nos cards de origem.
- [ ] O relatório diz tamanho da amostra, data e o que ficou inconclusivo.

## Testes

- Nenhum teste novo; os relatórios são a evidência.

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
