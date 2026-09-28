# CARD F20-01 — Baselines e relatórios da busca

- **Status:** Parcial — feito na máquina de referência em 2026-09-26. Baseline do F17-01
  medido e completo (`docs/pesquisas/baseline-f17-01.md`, marcado `Done`). Relatório do
  `eval_search.py` do F17-03 medido e versionado (`docs/pesquisas/eval-search-f17-03.md`),
  mas **inconclusivo** para o critério de aceite do F17-03 — viés conhecido na construção
  automática do conjunto de referência (as vagas "relevantes" foram escolhidas pelo mesmo
  critério de substring que o modo `like` usa, favorecendo-o por construção). F17-03 segue
  "Em revisão", não `Done`. A marcação de relevância (141 oportunidades, acima do mínimo
  de 100) usou uma heurística de título, não leitura humana descrição a descrição — ver
  limitação no relatório. Nenhum código de produção alterado, como pede este card (só
  `docs/pesquisas/` e os dois cards de origem).
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

## Addendum — rotulagem humana aplicada, sem resolver F17-03 (2026-09-27)

O revisor confirmou (`aceito`) as 98 recomendações de
`docs/44-roadmap-fase-20/rotulagem/f20-01-relevancia-busca.md` como estão, inclusive os 9
casos `ambíguo` (mantidos ambíguos, não promovidos). `data/search-reference/queries.json`
foi reconstruído localmente (fora do git) com as 86 linhas `relevante` — 14 consultas.
`docker compose -p opportunity-radar exec` (só leitura) + `eval_search.py --mode both`:
`like` recall@10 médio = 1,0000, `fulltext` = 0,8170. **Isso reconfirma o viés já
documentado, não o resolve**: os candidatos vieram de correspondência por título/empresa
(mesmo critério do `like`), então quase todo item confirmado como relevante já era um match
de `like` por construção. As duas consultas sem candidato por título (`kubernetes`,
`frontend` — as únicas que dariam ao full-text uma chance real) continuam sem gabarito,
pois exigem leitura de descrição completa fora do escopo desta sessão. **F17-03/F20-01
seguem "Em revisão"**, não `Done`.

## Addendum — gabarito por full-text sobre `description`, medição bloqueada (2026-09-28)

`docs/44-roadmap-fase-20/rotulagem/f20-01-relevancia-busca-fulltext.md` (branch
`feature/f20-rotulos-2`) resolve o viés apontado no addendum anterior: os 128 candidatos
(16 consultas × 8 vagas) agora vêm de `LIKE` sobre `description`, não sobre título/empresa.
68/128 (53%) recomendados como relevantes, 19 (15%) ambíguos, 41 (32%) não relevantes —
contra 98% de "relevante" no gabarito por título, porque agora o candidato pode ser um falso
positivo de verdade (`java`/`javascript`, `aws`/`laws`, `react`/`reactively`, `node`/`nodes`,
menção negada como `"NOT REQUIRED - machine learning"`, ou o termo descrevendo outra
equipe/o produto da empresa, não o cargo). `kubernetes` e `frontend` — sem candidato algum
no gabarito por título — tiveram 8/8 e 3/8 relevantes respectivamente.
`data/search-reference/queries.json` foi reconstruído localmente com as 68 linhas
`relevante`. **A rodada de `eval_search.py --mode both` não foi executada**: o Docker Desktop
da máquina caiu e voltou sozinho entre a cópia do `queries.json` para dentro do container e o
comando de avaliação (interrupção externa, não uma ação deste worker); os containers do
projeto `opportunity-radar` ficaram `Exited (255)` e este worker não os reiniciou, por
instrução explícita de nunca reiniciar o stack real. Comando pendente, documentado em
`f20-01-relevancia-busca-fulltext.md`:

```bash
docker cp data/search-reference/queries.json opportunity-radar-api-1:/app/data/search-reference/queries.json
docker exec opportunity-radar-api-1 python scripts/eval_search.py --mode both
```

**F17-03/F20-01 seguem "Em revisão"**: o gabarito agora é metodologicamente correto, mas os
números comparáveis `like` vs `fulltext` com este gabarito ainda faltam.

## Não fazer

- Não alterar código; este card só mede e documenta.
- Não inventar números: todo valor vem de uma saída de comando colada no relatório.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Os dois relatórios estão versionados e citados nos cards de origem.
- [x] O relatório diz tamanho da amostra, data e o que ficou inconclusivo.

## Testes

- Nenhum teste novo; os relatórios são a evidência.

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
