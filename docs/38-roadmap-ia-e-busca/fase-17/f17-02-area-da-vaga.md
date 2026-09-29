# CARD F17-02 — Área da vaga (`role-family-v1`) e filtro padrão na Inbox

- **Status:** Em revisão — evidência por critério abaixo (card F20-03); dois critérios
  de precisão/UNKNOWN dependem da medição no acervo real do F20-01
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-01, F18-07
- **Bloqueia:** F17-04 (habilitação em massa), F17-10, F17-11, Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §9

## Resultado

Toda vaga tem uma área classificada — engenharia, dados, produto, vendas… — com a evidência
que decidiu, e a Inbox mostra por padrão as áreas de interesse do perfil e UNKNOWN, sem apagar
nada.

## Contexto

Os coletores trazem o board inteiro da empresa. O departamento que o ATS informa (Ashby
`department`, Greenhouse `departments`) chega no `RawItem` e é descartado
(`acquisition/ashby.py:278`, `greenhouse.py:310`). Sem classificar a área, cada fonte nova
traz vendas, marketing e operações para a Inbox, e aumentar o volume piora a precisão.
É o card que permite os cards de volume.

## Escopo

- **Campo novo** na oportunidade: `role_family` (enum abaixo, `UNKNOWN` quando incerto),
  `role_family_evidence` (JSONB: regra, termo e origem que decidiram) e
  `role_family_version = "role-family-v1"`.
- **Áreas:** `SOFTWARE_ENGINEERING`, `DATA`, `INFRASTRUCTURE`, `SECURITY`, `QA`,
  `PRODUCT`, `DESIGN`, `SALES`, `MARKETING`, `OPERATIONS`, `PEOPLE`, `FINANCE`, `LEGAL`,
  `SUPPORT`, `OTHER`, `UNKNOWN`.
- **Regra determinística**, nesta ordem de precedência:
  1. departamento do ATS, por tabela de mapeamento (português e inglês, normalizado);
  2. padrões no título (ex.: "engineer|developer|desenvolvedor|engenheiro de software" →
     engenharia; "data (engineer|scientist|analyst)|cientista de dados" → dados;
     "account executive|sdr|vendas" → vendas), com prioridade para o padrão mais
     específico;
  3. termos da descrição só como desempate entre duas áreas empatadas pelo título.
- **Retroativo:** job ou script que classifica as oportunidades existentes a partir do
  título e do departamento guardado no `RawItem` (`collected_item_v1.metadata`).
- **Perfil:** preferência nova `target_role_families` (lista) na versão do perfil, editável
  na tela de perfil. Perfil sem a preferência = todas as áreas, como hoje.
- **Inbox:** filtro de área, ligado por padrão nas áreas do perfil e em UNKNOWN, com contador "N vagas
  em outras áreas" e um clique para ver todas.
- **Métrica:** taxa de `UNKNOWN` no relatório do F17-01.

## Fora de escopo

- Novo fator no matching: mudaria o `rules_version` e reavaliaria o acervo inteiro. Fica
  para avaliação depois de medir o filtro.
- Classificação por modelo de linguagem.

## Notas de implementação

- A tabela de departamentos e os padrões de título moram num módulo versionado
  (`opportunities/role_family.py`), com teste por linha da tabela.
- "Solutions Engineer", "Sales Engineer", "Developer Advocate" são os casos de fronteira
  mais comuns: decidir pelo departamento quando existir; sem departamento, `UNKNOWN` é
  melhor que chute.
- Mudar a regra é nova versão (`role-family-v2`), com reclassificação retroativa.

## Critérios de aceite

- [ ] Vagas novas saem da normalização com área, evidência e versão.
- [ ] As vagas existentes são reclassificadas retroativamente.
- [ ] O perfil declara áreas de interesse, e a Inbox as usa como filtro padrão.
- [ ] Nenhuma vaga fora do filtro deixa de ser encontrável.
- [ ] Taxa de UNKNOWN medida; < 10% é alvo secundário, sem adivinhar classificação.
- [ ] Precisão por área e perda de relevantes pelo filtro são medidas no conjunto
      reservado; nenhuma redução de UNKNOWN compensa aumento de falso descarte.
- [ ] UNKNOWN permanece visível por padrão; ver todas preserva o acervo.
- [ ] Reclassificação aplica regra nova sem depender de timestamp externo (F17-06).

## Verificação

- **CI:** testes unitários da regra com uma tabela de títulos reais (≥ 60, cobrindo todas
  as áreas e as fronteiras); teste do retroativo; teste da Inbox com e sem a preferência;
  E2E conferindo `role_family` na oportunidade do ciclo.
- **Máquina de referência:** precisão da Inbox antes e depois, pelo relatório do F17-01.

## Critério → evidência (card F20-03)

| Critério | Evidência |
| --- | --- |
| Vagas novas saem com área, evidência e versão | `tests/backend/opportunities/test_domain.py::test_candidate_carries_the_role_family_decision_and_its_evidence` |
| Vagas existentes reclassificadas retroativamente | `tests/backend/test_role_family_integration.py::test_reclassify_role_families_updates_only_stale_rows`, `scripts/reclassify_role_families.py` |
| Perfil declara áreas; Inbox usa como filtro padrão | `tests/backend/dashboard/test_queries.py::test_inbox_filters_by_role_family_without_deleting_off_filter_rows` |
| Nenhuma vaga fora do filtro deixa de ser encontrável / UNKNOWN visível por padrão | mesmo teste acima (`...without_deleting_off_filter_rows`) confirma que a linha fora do filtro continua na consulta, só marcada |
| Reclassificação usa versão, não timestamp externo | `scripts/reclassify_role_families.py` só toca `role_family_version` divergente da atual; `test_reclassify_role_families_updates_only_stale_rows` |
| Taxa de UNKNOWN medida (< 10% é meta secundária) | sem evidência verificável nesta revisão — depende da medição no acervo real; ver [F20-01](../../../44-roadmap-fase-20/fase-20/f20-01-baselines-e-relatorios-da-busca.md) |
| Precisão por área e perda de relevantes no conjunto reservado | sem evidência verificável nesta revisão — mesma dependência do F20-01 |

## Arquivos prováveis

- `src/opportunity_radar/opportunities/role_family.py` (novo), `domain.py`, `service.py`,
  `models.py`
- `src/opportunity_radar/profile/domain.py`, `profile/models.py`
- `src/opportunity_radar/dashboard/queries.py`
- `migrations/versions/*_role_family.py`
- `apps/web/src/routes/InboxPage.tsx`, `ProfilePage.tsx`
