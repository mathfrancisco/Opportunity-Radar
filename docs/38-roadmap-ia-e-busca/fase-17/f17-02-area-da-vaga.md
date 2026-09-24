# CARD F17-02 — Área da vaga (`role-family-v1`) e filtro padrão na Inbox

- **Status:** Backlog
- **Fase:** 17 — Busca de vagas: cobertura e precisão
- **Depende de:** F17-01
- **Bloqueia:** F17-04 (habilitação em massa), F17-10, F17-11, Milestone P
- **Origem:** [SPEC de busca](../../37-spec-busca.md), §9

## Resultado

Toda vaga tem uma área classificada — engenharia, dados, produto, vendas… — com a evidência
que decidiu, e a Inbox mostra por padrão só as áreas de interesse do perfil, sem apagar
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
- **Inbox:** filtro de área, ligado por padrão nas áreas do perfil, com contador "N vagas
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
- [ ] Taxa de `UNKNOWN` < 10% no acervo, medida no relatório do F17-01.

## Verificação

- **CI:** testes unitários da regra com uma tabela de títulos reais (≥ 60, cobrindo todas
  as áreas e as fronteiras); teste do retroativo; teste da Inbox com e sem a preferência;
  E2E conferindo `role_family` na oportunidade do ciclo.
- **Máquina de referência:** precisão da Inbox antes e depois, pelo relatório do F17-01.

## Arquivos prováveis

- `src/opportunity_radar/opportunities/role_family.py` (novo), `domain.py`, `service.py`,
  `models.py`
- `src/opportunity_radar/profile/domain.py`, `profile/models.py`
- `src/opportunity_radar/dashboard/queries.py`
- `migrations/versions/*_role_family.py`
- `apps/web/src/routes/InboxPage.tsx`, `ProfilePage.tsx`
