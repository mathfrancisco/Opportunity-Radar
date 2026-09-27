# CARD F20-02 — Curadoria manual de `skills-v2`

- **Status:** Feito — `scripts/unmatched_skill_terms.py` rodado contra o acervo real (648
  oportunidades, 630 descrições), saída e decisão por termo em
  `docs/pesquisas/curadoria-skills-v2.md`. Três entradas novas na `SKILL_TAXONOMY` (`ai`,
  `cicd`, `observability`) com testes de regressão usando texto real.
  `SKILL_TAXONOMY_VERSION` subiu para `skills-v2` e o reprocessamento oficial rodou na
  máquina de referência (bump de `NORMALIZER_VERSION` para `v4`,
  `POST /opportunities/normalizations/pending` até esvaziar a fila): cobertura de skills
  48,46% → 90,74% confirmada pelo pipeline de verdade (não mais pela reextração ad-hoc),
  sem perder oportunidade e sem falha nova. Ver
  `docs/pesquisas/curadoria-skills-v2.md` (seção "Reprocessamento oficial") para a
  medição completa e a lista de arquivos tocados além da lista original (`service.py`,
  `domain.py`, mais os testes com o literal `"skills-v1"` que dependiam do valor padrão).
  F17-06 segue "Em revisão", não `Done`: o reprocessamento não regrediu evidência de
  skill, mas revelou que o critério de `seniority-v2` (reduzir `UNKNOWN` à metade) não
  está sendo atingido no acervo real (328/648 = 50,62%, igual ao baseline) — achado fora
  do escopo deste card, registrado no F17-06.
- **Fase:** 20 — IA cloud e consolidação
- **Bloco:** A — Fechamento do que está em revisão
- **Depende de:** Nenhum
- **Origem:** [SPEC 43](../../43-spec-llm-cloud-e-consolidacao.md); [F17-06](../../38-roadmap-ia-e-busca/fase-17/f17-06-normalizacao-mais-precisa.md)

## Resultado

As lacunas de skill encontradas por `scripts/unmatched_skill_terms.py` viram entradas revisadas de `skills-v2`, com aliases e desambiguação, e o F17-06 fecha.

## Contexto

O F17-06 entregou `seniority-v2`, `regions-v1`, reprocessamento e o script de lacunas (`c599c09`, `1f02ba3`, `23ca1de`). Falta a curadoria manual. O teste `tests/backend/test_unmatched_skill_terms.py` cobre o script.

## Arquivos

| Ação | Caminho | O quê |
| --- | --- | --- |
| Alterar | `arquivo da taxonomia `skills-v2` (localizar com `grep -rn "skills-v2" src`)` | entradas novas e aliases |
| Criar | `docs/pesquisas/curadoria-skills-v2.md` | saída do script e decisão por termo |
| Alterar | `tests/backend/opportunities/ (arquivo de teste da taxonomia existente)` | casos de regressão |

## Passos

1. Rodar `python scripts/unmatched_skill_terms.py` no acervo real e salvar a saída em `curadoria-skills-v2.md`.
2. Para cada termo, decidir e anotar: `nova skill`, `alias de <skill>`, `ambíguo` (com a regra) ou `descartado`.
3. Aplicar as decisões na taxonomia e subir a versão (ex.: `skills-v2` → `skills-v3`) se o formato do projeto exigir versão nova por mudança.
4. Para cada entrada nova ou alias, adicionar um caso de teste com um texto real de vaga.
5. Rodar o reprocessamento retomável do F17-06 e anotar antes/depois da cobertura de skills no documento.
6. Marcar o F17-06 como `Done`.

## Não fazer

- Não mudar a regra de senioridade nem de regiões neste card.
- Não alterar elegibilidade, score, veredito nem fatores do matching.
- Não tocar em arquivo fora da lista "Arquivos" sem registrar o motivo no PR.
- Não adicionar dependência nova em `requirements*.txt` (o projeto usa `httpx`, `pydantic`, `sqlalchemy`, `alembic`).
- Não fazer chamada real ao Groq nos testes; usar `httpx.MockTransport`.
- Não logar nem serializar `GROQ_API_KEY`.

## Critérios de aceite

- [x] Toda entrada nova tem teste de regressão.
- [x] O reprocessamento não regride evidência existente. Reprocessamento oficial rodado
      na máquina de referência (`NORMALIZER_VERSION` v3 → v4): 648 oportunidades antes e
      depois, cobertura de skill 48,46% → 90,74%, zero linha `opportunity_skill` órfã em
      `skills-v1`, 22 falhas `INVALID_COLLECTED_ITEM_V1` idênticas antes/depois (nenhuma
      nova). Prova também por construção:
      `tests/backend/opportunities/test_domain.py::test_skills_v2_never_removes_or_narrows_a_skills_v1_entry`
      (a `skills-v2` só adiciona entradas, nunca remove/estreita uma da `skills-v1`). Ver
      `docs/pesquisas/curadoria-skills-v2.md`. Reprocessamento seguinte
      (`NORMALIZER_VERSION` v4 → v5, remoção do alias `ci`) também rodado e verificado
      contra o acervo real — ver
      `docs/44-roadmap-fase-20/evidencias/reprocessamento-skills-v3-2026-09-27.md`: 648
      oportunidades antes e depois, zero linha `opportunity_skill` órfã em `skills-v2`, 22
      falhas idênticas (mesmo `raw_item_id`) antes/depois.
- [ ] F17-06 marcado como Done com link para `curadoria-skills-v2.md`. **Não marcado:**
      a curadoria e o reprocessamento de `skills-v2` fecham, mas o reprocessamento real
      revelou que o critério de `seniority-v2` do F17-06 (`UNKNOWN` à metade do baseline)
      não é atingido no acervo (328/648 = 50,62%, igual ao baseline 50,6%) — achado que
      exige investigação fora do escopo deste card, fica registrado no F17-06 como
      pendência que bloqueia o `Done` do card inteiro.

**Follow-up de rotulagem humana (2026-09-27):** as 11 decisões de
`docs/44-roadmap-fase-20/rotulagem/f20-02-curadoria-skills-v2.md` foram confirmadas
(`aceito`). A única mudança de conteúdo (remover o alias solto `ci` de `cicd`, porque 82%
das 218 ocorrências reais vinham de "CI&T", nome da empresa, não de CI/CD) foi aplicada em
`src/opportunity_radar/opportunities/domain.py`. Por mudar o conjunto de aliases,
`SKILL_TAXONOMY_VERSION` subiu de `"skills-v2"` para `"skills-v3"` e `NORMALIZER_VERSION`
subiu de `"v4"` para `"v5"` (`service.py`), seguindo a mesma convenção do bump v1→v2; os
literais de "versão atual" em `tests/backend/opportunities/test_domain.py` e
`tests/backend/test_opportunities_integration.py`, e os dois literais `taxonomy_version`
em `.github/workflows/pipeline.yml`, foram atualizados para `"skills-v3"`. Novo teste
`test_removes_the_bare_ci_alias_that_false_matched_the_company_name` prova, com texto real
do acervo, que "CI&T, we help large enterprises..." não gera `cicd` e que "CI/CD pipeline"
continua gerando. Suíte completa roda verde (860 passed, 1 falha pré-existente e não
relacionada em `test_delta_presence_resume.py`, confirmada flaky/isolada — ver evidência no
handback da sessão).

**Reprocessamento oficial (2026-09-27, sessão de fechamento da pendência):** rodado contra
o acervo real (projeto compose `opportunity-radar`) via
`POST /opportunities/normalizations/pending?limit=500` até `processed=0`, depois de um
backup verificado (`data/backups/f20-02-pre-skills-v3-2026-09-27.dump`, `restore check
passed`) e de reconstruir as imagens `migrate`/`api`/`worker` (estavam anteriores ao
arquivo de migração `20260926_0043`, que já estava aplicado no banco — nenhuma migração de
schema nova nesta branch). Ver
`docs/44-roadmap-fase-20/evidencias/reprocessamento-skills-v3-2026-09-27.md` para os
comandos completos e a medição linha a linha. Resumo: 648 oportunidades antes e depois
(nenhuma perdida/duplicada), `opportunity_skill` 1844 linhas `skills-v2` → 1735 linhas
`skills-v3` (zero linha `skills-v2` órfã), hits de `cicd` 221 → 112 (queda de exatamente
109, igual à queda de linhas — só o alias `ci` foi afetado), cobertura de skill 90,74% →
90,59% (queda esperada: a oportunidade cuja única evidência era o falso positivo "CI&T"
perdeu a linha), 22 falhas `INVALID_COLLECTED_ITEM_V1` sob `v5`, **mesmo conjunto** de
`raw_item_id` das falhas sob `v4` (nenhuma falha nova). A base real não tem mais nenhuma
linha `opportunity_skill` em `skills-v2`.

## Testes

- Um caso por alias e por regra de desambiguação no arquivo de teste da taxonomia.

## Comando de verificação

```bash
docker compose -p f20-02 -f compose.yaml -f compose.dev.yaml run --rm api pytest -q tests/backend/opportunities tests/backend/test_unmatched_skill_terms.py
docker compose -p f20-02 -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
docker compose -p f20-02 -f compose.yaml -f compose.dev.yaml run --rm api mypy
```

## Pronto quando

Todos os critérios de aceite estão marcados, o comando de verificação passa e o CI está verde.
