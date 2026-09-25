# CARD F17-03 — Busca full-text, sinônimos e filtros combináveis

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-01, F17-02
- **Bloqueia:** F16-10, F17-12, Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §10

## Resultado

A busca da Inbox encontra a vaga pelo que está escrito nela — título, empresa, skills e
descrição —, entende plural, acento e sinônimo do domínio, e combina o termo com filtros.

## Contexto

Hoje a busca é `LIKE '%termo%'` em título e empresa (`dashboard/queries.py:345`).
"Kubernetes", "remoto LATAM" ou "pleno" só aparecem na descrição e não são achados;
"desenvolvedora" não acha "desenvolvedor"; e o resultado não tem ordem de relevância.

## Escopo

- **Documento de busca** na oportunidade: coluna `search_skills text` (nomes das skills,
  mantida pela normalização) e coluna gerada `search_document tsvector` com pesos:
  título (A), empresa (A), skills e área (B), descrição (C), local (D). Duas configurações
  combinadas: `portuguese` e `english`. Índice GIN.
- **Acento:** extensão `unaccent` com função imutável própria (`f_unaccent`) para caber
  em coluna gerada.
- **Consulta:** `websearch_to_tsquery` nas duas configurações, `OR` entre elas; ordenação por
  `ts_rank_cd` quando há termo; sem termo, a ordem atual.
- **Sinônimos do domínio:** módulo versionado (`dashboard/search_synonyms.py`,
  `synonyms-v1`) aplicado na consulta: desenvolvedor/developer/engineer/engenheiro,
  sênior/senior/sr, pleno/mid/mid-level, júnior/junior/jr, remoto/remote, dados/data,
  vaga/job. Mudar o dicionário não exige reindexar.
- **Filtros combináveis** com o termo: área (F17-02), senioridade, modo de trabalho, país
  permitido, faixa de remuneração, empresa, fonte, "publicada nos últimos N dias". Na
  tela, filtros visíveis e refletidos na URL.
- **Avaliação:** `scripts/eval_search.py --mode fulltext` sobre o conjunto de referência do
  F17-01: recall@10 e nDCG@10 antes (LIKE) e depois, no PR.

## Fora de escopo

- Busca por significado (F16-10).
- Buscas salvas (F17-12).

## Notas de implementação

- Coluna gerada só pode usar colunas da mesma tabela e funções imutáveis; por isso skills
  entram pela coluna desnormalizada `search_skills`, e `unaccent` pela função wrapper.
- `unaccent` é contrib e vem nas imagens oficiais do Postgres, inclusive a alpine com
  pgvector do F16-09.
- A migração recalcula a coluna para o acervo existente; em acervo grande, fazer o
  `ALTER` fora do horário de coleta.

## Contrato de consulta

- Mesmo universo de filtros da busca semântica; empate por rank, data e id.
  Ordenação/paginação não pode repetir ou perder linha por empate.
- Atualizar documento ao mudar empresa canônica, skills, área ou texto, inclusive
  em reprocessamento; não apenas na primeira inserção.
- Sinônimos preservam frases, negação e AND/OR da consulta; não expandir substring
  indiscriminadamente. Casos como C++, C#, .NET e Node.js entram na referência.
- Perfil/filtro desconhecido não vira exclusão implícita. Fonte filtra ocorrências,
  não duplica a oportunidade quando há várias fontes.
- Reportar P@10, recall@10 e nDCG@10 no corpus congelado, além da latência p95
  com volume representativo. Este modo opera sem Ollama.

## Critérios de aceite

- [ ] Termo presente só na descrição é encontrado.
- [ ] Busca sem acento acha texto com acento, e plural acha singular.
- [ ] Sinônimos do dicionário ampliam a busca.
- [ ] Todos os filtros combinam entre si e com o termo, refletidos na URL.
- [ ] recall@10 do full-text > recall@10 do LIKE no conjunto de referência.

## Verificação

- **CI:** testes de integração com vagas fixas cobrindo descrição, acento, plural,
  sinônimo, pesos (título acima de descrição) e cada filtro; teste do módulo de
  sinônimos; E2E buscando por um termo que só existe na descrição da vaga do ciclo.
- **Máquina de referência:** relatório do `eval_search.py` anexado ao PR.

## Arquivos prováveis

- `migrations/versions/*_search_document.py`
- `src/opportunity_radar/dashboard/queries.py`, `dashboard/search_synonyms.py` (novo)
- `src/opportunity_radar/opportunities/service.py` (manutenção de `search_skills`)
- `src/opportunity_radar/presentation/http/dashboard.py`
- `apps/web/src/routes/InboxPage.tsx`, `apps/web/src/features/dashboard/`
- `scripts/eval_search.py` (novo, compartilhado com F16-10)
