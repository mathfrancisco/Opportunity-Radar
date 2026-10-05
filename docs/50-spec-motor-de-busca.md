# SPEC — Motor de busca e análise: vagas classificadas, menos ruído, menos IA (cards F50)

- **Status:** Em implementação na branch `f50-motor-de-busca`, ainda sem deploy. O estado de
  cada card está em [STATUS](50-roadmap-motor-de-busca/STATUS.md). As correções entregues
  antes desta spec estão no §2 e não fazem parte do escopo.
- **Data:** 2026-10-05
- **Base verificada:** branch `spec-46-redesign-ui` (`75d688b`) e o banco da stack
  `spec46full` (volume `opportunity-radar-recovery-a7a43`), lido em 2026-10-05 entre 01:00Z e
  03:00Z. O worker estava coletando e avaliando durante a leitura, então contagens de
  matching são de um instante.
- **Escopo:** fazer o motor entregar ao perfil ativo uma lista curta de vagas elegíveis e bem
  classificadas, gastando a cota de IA só onde ela muda uma decisão. Cobre coleta,
  normalização, matching, fila de análise e o custo de leitura do Inbox.
- **Fora de escopo:** novas fontes ou novos coletores (SPEC 48 e doc 49), redesign de UI
  (SPEC 46), troca de provedor de IA.
- **Convenções:** o que foi medido no banco ou lido no código vem sem marca. O que é
  **inferido** vem marcado *(inferido)* e precisa ser confirmado no card antes de implementar.
  Escalas: esforço P (até meio dia), M (até 2 dias), G (mais de 2 dias); risco baixo, médio,
  alto.
- **Documentos relacionados:** [Arquitetura atual (47)](47-arquitetura-atual.md),
  [SPEC 48 — mais vagas](48-spec-mais-vagas.md),
  [SPEC 43 — LLM cloud](43-spec-llm-cloud-e-consolidacao.md),
  [Matching e scoring (20)](20-matching-scoring.md).

---

## 1. Objetivo e métricas

O motor é bom quando o usuário abre o Inbox e as primeiras páginas são vagas a que ele pode
se candidatar. Hoje o catálogo tem 25 mil vagas e o motor não consegue dizer, para mais de
90% delas, se o perfil é elegível.

| Métrica | Hoje | Meta |
|---|---|---|
| Vagas com `allowed_countries` preenchido | 6% | ≥ 60% das vagas das áreas-alvo |
| Vagas com `work_mode` conhecido | 29% | ≥ 70% das vagas das áreas-alvo |
| Vagas com `seniority` conhecida | 44% | ≥ 70% das vagas das áreas-alvo |
| Vagas com `role_family` conhecida | 71% | ≥ 90% |
| Avaliações com elegibilidade decidida (`ELIGIBLE` ou `INELIGIBLE`) | 15% (só `INELIGIBLE`; zero `ELIGIBLE`) | ≥ 50% das áreas-alvo |
| Parcela do catálogo nas áreas-alvo do perfil | ~28% | ≥ 60% |
| Chamadas de IA repetidas para a mesma vaga | 61% (antes de `5c7f089`) | ≤ 5% |
| Linhas novas em `match_assessment` por dia | ~25 mil | proporcional ao que mudou |
| `/inbox` p95 | ~6s | ≤ 1,5s |

As metas de preenchimento são propostas; o card F50-01 mede a linha de base por fonte antes
de qualquer mudança e ajusta as metas se o gold set mostrar que são inalcançáveis.

**Revisão de 2026-10-05.** A coluna "Hoje" continua valendo: o código da branch não foi
aplicado na stack, então nenhuma métrica mudou. O que as medições já dizem sobre as metas:

- `allowed_countries` ≥ 60% não é alcançável com as regras atuais. Elas cobrem 11,5% das
  vagas com descrição
  ([linha de base](pesquisas/f50-01-linha-de-base-classificacao.md)). A meta fica em aberto
  até o gold rotulado existir.
- `seniority` ≥ 70% é alcançável (62,2% de cobertura); `work_mode` ≥ 70% é incerta (39,3%).
- Elegibilidade decidida ≥ 50% não sai só do F50-06: depois dele, quem segura a elegibilidade
  é senioridade e contrato desconhecidos. Contrato ficou fora da Q3.
- A skill `ai` cai de 40% para 24,1% do catálogo com a taxonomia `skills-v4`, acima da meta
  de 15%.

---

## 2. Estado atual

### 2.1 Funil medido (2026-10-05)

| Etapa | Número |
|---|---|
| Fontes habilitadas | 137 de 147 |
| Execuções de coleta | 509 |
| Itens brutos | 33.437 |
| Vagas | 25.112 (24.889 abertas) |
| Vagas avaliadas (perfil de teste) | 25.112 |
| Vagas reavaliadas com o perfil real | 9.712 (worker em andamento) |
| Análises de IA concluídas | ~490 |
| Análises falhas por `QUOTA_EXHAUSTED` | 2.213 |

### 2.2 Já entregue nesta rodada (não repetir)

| Commit | O que mudou |
|---|---|
| `ecf8100` | Índice `ix_source_occurrence_opportunity` (migração `20261004_0061`) e Inbox ranqueado em passo único. `/inbox`, `/overview` e `/search-metrics` saíram de mais de 2 minutos para ~6s. |
| `5c7f089` | Chave de análise `analysis-key-v4`: ignora versão da linha, referências de evidência e score. |
| `f38d2e4` | Fila de análise restrita às áreas-alvo do perfil; padrão `WORKER_ANALYZE_VERDICTS=HIGH_PRIORITY,RECOMMENDED`. |
| — | Perfil real ativo no banco do `spec46full` (versão 2). Não está no repositório. |

### 2.3 Problemas em aberto

**P1. Campos das vagas vazios.** Percentual de vagas sem o campo, por tipo de fonte:

| Fonte | Vagas | `work_mode` | `seniority` | `role_family` | `allowed_countries` | sem descrição | sem skills |
|---|---|---|---|---|---|---|---|
| workday | 10.519 | 97% | 58% | 51% | 100% | 100% | 94% |
| greenhouse | 7.189 | 77% | 51% | 14% | 93% | 0% | 19% |
| lever | 2.931 | 0% | 55% | 5% | 84% | 1% | 30% |
| ashby | 2.769 | 38% | 57% | 11% | 84% | 0% | 7% |
| workable | 803 | 98% | 75% | 42% | 100% | 0% | 32% |
| teamtailor | 438 | 50% | 80% | 25% | 100% | 0% | 74% |

Os classificadores que leem a descrição (`seniority-v4`, `work-mode-v7`,
`allowed-countries-v2`) existem e estão desligados
(`content_classification_v4_enabled = False`, `platform/config.py`), aguardando o portão de
90% de precisão por regra em `scripts/measure_content_classification.py --check-gate`.

**P2. Elegibilidade nunca fecha.** Em 10.865 avaliações medidas, `COUNTRY_ALLOWED` ficou
`UNKNOWN` em 97%, `CONTRACT_COMPATIBLE` em 94%, `SENIORITY_COMPATIBLE` em 90%, e
`TIMEZONE_COMPATIBLE` e `WORK_AUTHORIZATION_COMPATIBLE` em 100%. Nenhuma avaliação saiu
`ELIGIBLE`. Fatores `UNKNOWN` recebem nota neutra 0,5, então o score se concentra entre 40 e
60 e o veredito vira `WATCHLIST` para a maior parte do catálogo (4.536 de 9.712 com o perfil
real). P2 é consequência de P1, mais dois critérios que não têm fonte de dado nenhuma (fuso
e autorização de trabalho).

**P3. Workday é volume sem conteúdo.** 42% do catálogo vem de 15 fontes Workday, que chegam
sem descrição. Parcela de vagas de tecnologia nas maiores: Abbott 11% (2.147 vagas), Chanel
3% (1.096), Santander 5% (915), Procter & Gamble 18% (822), Accenture 28% (1.155). O coletor
Workday guarda só a listagem *(inferido: o detalhe da vaga exige uma segunda chamada por
vaga, que o coletor não faz)*.

**P4. Taxonomia de skills curta e a skill `ai` casa demais.** A taxonomia em uso tem 30
skills. `ai` aparece em 10.161 vagas (40% do catálogo), contra 2.523 de `python`. O fator
`TECHNOLOGY_FIT` (peso 0,25) ficou `UNKNOWN` em 94% das avaliações. Faltam skills do perfil
ativo: Spring Boot, NestJS, Vue, React Native, RAG, LLM.

**P5. O catálogo inteiro é reavaliado todo dia.** `pending_evaluation_ids`
(`matching/service.py`) exige uma avaliação com o mesmo dia de referência UTC, então cada
vaga aberta ganha uma avaliação nova por dia: ~25 mil linhas em `match_assessment` e ~200 mil
em `match_factor`. O único fator que depende da data é `RECENCY` (peso 0,05). A fila é
ordenada por `created_at`, sem prioridade por área. Não há poda de avaliações antigas
*(inferido: `expire_raw_payloads` cuida de payloads e de `ai_call_record`, não de
avaliações)*.

**P6. Prompt de análise carrega peso morto.** Média de 1.116 tokens de entrada e 571 de
saída por análise, contra um orçamento diário de 170.000 tokens (`AI_DAILY_TOKENS_SOFT_LIMIT`),
ou ~100 análises por dia. O payload envia `evidence_refs` e `skill_evidence_refs` (UUIDs e
hashes SHA-256) que o modelo não usa para citar evidência: `evidence_sources`
(`matching/analysis.py`) aceita só trechos de `posting`, `opportunity` e `profile`.

**P7. Leitura do Inbox ainda custa ~6s.** Cada request recalcula a avaliação mais recente de
todas as vagas (`_latest_assessments`, `dashboard/queries.py`) sobre uma tabela que cresce
25 mil linhas por dia (P5), e a lista é executada duas vezes (contagem e página), ou três
quando há filtro de área.

**P8. Pendências menores.**
- `opportunity_embedding` tem 0 linhas; o job `embed_opportunities` não roda desde
  2026-09-25.
- 107 `duplicate_candidate` em `PENDING`, todos da regra `title_location_window`.
- A fonte Hacker News termina sempre `PARTIAL` com `INVALID_ITEM` (19 comentários sem empresa
  ou cargo identificável em cada execução).
- 4.809 normalizações em `REVIEW_REQUIRED`, quase todas por
  `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`.
- Queries órfãs: quando o cliente desiste, a query do Inbox continua rodando no Postgres. Não
  há `statement_timeout` na conexão da API.

---

## 3. Cards

Ordem de execução no §4. Cada card é entregue sozinho, com teste, e medido contra o §1.

### F50-01 — Linha de base e gold set por fonte

- **Problema:** P1. As metas do §1 não têm linha de base por regra nem por fonte.
- **Mudança:** rodar `scripts/measure_content_classification.py` no catálogo atual e
  registrar precisão e cobertura de `seniority-v4`, `work-mode-v7` e `allowed-countries-v2`
  por tipo de fonte. Completar o gold set rotulado até ter no mínimo 50 vagas por tipo de
  fonte com descrição.
- **Aceite:** relatório em `docs/pesquisas/` com precisão e cobertura por regra e por fonte;
  metas do §1 confirmadas ou corrigidas.
- **Teste:** o script roda no CI contra o gold set versionado.
- **Esforço / risco:** M / baixo. Sem mudança de comportamento.

### F50-02 — Ligar a classificação por descrição

- **Problema:** P1, P2.
- **Mudança:** para cada regra que passar o portão de 90% no F50-01, ligar
  `content_classification_v4_enabled` e reclassificar o catálogo existente em lotes. Regra
  que não passar fica desligada e vira item do F50-01.
- **Aceite:** metas de preenchimento do §1 atingidas nas áreas-alvo; nenhuma regra ligada
  abaixo de 90% de precisão.
- **Teste:** testes de regressão por regra sobre o gold set; teste de que a reclassificação
  em lote incrementa a versão da vaga uma única vez.
- **Esforço / risco:** M / médio. Reclassificar muda vereditos; rodar primeiro em cópia do
  banco e comparar a distribuição.
- **Depende de:** F50-01.

### F50-03 — Detalhe das vagas Workday, só para áreas-alvo

- **Problema:** P3.
- **Mudança:** classificar `role_family` pelo título no momento da coleta. Para vagas Workday
  nas áreas-alvo, buscar o detalhe (descrição) respeitando o `rate_limit_policy` e o
  orçamento por host. Vagas fora das áreas-alvo ficam só com a listagem.
- **Aceite:** ≥ 90% das vagas Workday das áreas-alvo com descrição; número de requisições por
  execução dentro do orçamento do host.
- **Teste:** teste do coletor com fixture de listagem e de detalhe; teste de que vaga fora da
  área não gera segunda chamada.
- **Esforço / risco:** G / médio. Confirmar antes que o endpoint de detalhe está coberto pela
  revisão de termos da fonte.
- **Pergunta aberta:** Q1.

### F50-04 — Corte de ruído na coleta

- **Problema:** P3. Vagas de vendas, operações, jurídico e finanças ocupam avaliação, índice
  e tela.
- **Mudança:** registrar, por fonte, a parcela de vagas nas áreas-alvo das últimas execuções.
  Fonte abaixo de um piso configurável passa a persistir só as vagas das áreas-alvo e de
  `role_family = UNKNOWN`. Vagas fora da área já persistidas saem do filtro padrão do Inbox
  (já é o comportamento com `target_role_families`) e da fila de avaliação.
- **Aceite:** parcela do catálogo nas áreas-alvo ≥ 60%; nenhuma vaga das áreas-alvo perdida
  em comparação com uma execução sem o filtro, medida em três fontes.
- **Teste:** teste de serviço de coleta com fonte acima e abaixo do piso.
- **Esforço / risco:** M / médio. Depende da precisão de `role_family` pelo título; por isso
  `UNKNOWN` nunca é descartado.
- **Pergunta aberta:** Q2.

### F50-05 — Taxonomia de skills

- **Problema:** P4.
- **Mudança:** restringir a regra de `ai` a termos específicos (LLM, RAG, machine learning,
  agentes) em vez da palavra solta. Acrescentar as skills ausentes do perfil ativo e as mais
  frequentes nas descrições das áreas-alvo. Incrementar a versão da taxonomia.
- **Aceite:** `ai` em menos de 15% do catálogo; `TECHNOLOGY_FIT` com status `KNOWN` em ≥ 50%
  das vagas das áreas-alvo com descrição.
- **Teste:** casos positivos e negativos por skill nova; amostra rotulada de 100 vagas para
  `ai`.
- **Esforço / risco:** M / médio. Mudar a taxonomia invalida todas as avaliações uma vez.

### F50-06 — Elegibilidade com o que se sabe

- **Problema:** P2. Fuso e autorização de trabalho ficam `UNKNOWN` em 100% das avaliações
  porque não há dado de origem, e travam a elegibilidade junto com os demais.
- **Mudança:** critério sem fonte de dado no catálogo deixa de contar como `UNKNOWN` na
  elegibilidade e passa a `NOT_APPLICABLE`, sem alterar o score. A elegibilidade fecha em
  `ELIGIBLE` quando todos os critérios com dado são `TRUE`. Incrementar `RULES_VERSION`.
- **Aceite:** ≥ 50% das avaliações das áreas-alvo com elegibilidade decidida, depois de
  F50-02.
- **Teste:** tabela de casos de elegibilidade; regressão `matching-v2` atualizada de forma
  explícita.
- **Esforço / risco:** M / alto. Muda a regra de decisão. Exige a decisão da Q3 antes.
- **Depende de:** F50-02.

### F50-07 — Reavaliar só o que mudou

- **Problema:** P5.
- **Mudança:** tirar o dia de referência da identidade da avaliação. A fila passa a conter
  vagas sem avaliação para a identidade atual (versão da vaga, perfil, regras, taxonomia) e
  vagas cujo fator `RECENCY` cruzou uma faixa desde a última avaliação. Ordenar a fila por
  área-alvo primeiro.
- **Aceite:** em um dia sem recoleta e sem mudança de perfil, a fila processa menos de 5% do
  catálogo; o score de uma vaga antiga continua caindo quando ela cruza uma faixa de
  recência.
- **Teste:** atualizar `tests/backend/matching/test_evaluation_queue.py` e
  `test_reevaluation.py`; o caso "o próximo dia UTC" vira "a vaga cruzou a faixa".
- **Esforço / risco:** M / médio. Toca `matching/currency.py` e o espelho em SQL do Inbox
  (`is_current_assessment`); os dois precisam mudar juntos.

### F50-08 — Poda de avaliações antigas

- **Problema:** P5, P7.
- **Mudança:** job de retenção que apaga avaliações substituídas há mais de N dias, mantendo
  sempre a mais recente por vaga e por perfil e qualquer avaliação com análise de IA ou
  candidatura ligada.
- **Aceite:** `match_assessment` estabiliza em no máximo três linhas por vaga aberta, em
  média.
- **Teste:** teste de integração da poda cobrindo as três exceções.
- **Esforço / risco:** P / médio. É exclusão de dados: rodar com `--dry-run` primeiro e só
  ligar no worker depois de conferir o relatório.

### F50-09 — Prompt de análise menor

- **Problema:** P6.
- **Mudança:** tirar `evidence_refs` e `skill_evidence_refs` do payload enviado; reduzir o
  teto de saída ao que o schema precisa; limitar o número de itens de `strengths`, `risks`,
  `inferences` e `unknowns` no schema. É uma nova versão de prompt.
- **Aceite:** tokens de entrada médios ≤ 800 e de saída ≤ 350, sem queda na avaliação do
  prompt (`prompts/opportunity_analysis/eval`).
- **Teste:** suíte de avaliação do prompt na versão nova comparada com a `v1`.
- **Esforço / risco:** M / médio. Versão nova de prompt invalida o cache de análises uma vez.

### F50-10 — Leitura do Inbox abaixo de 1,5s

- **Problema:** P7, P8 (queries órfãs).
- **Mudança:** materializar a avaliação atual por vaga em uma tabela mantida na escrita da
  avaliação, e fazer o Inbox ler dela. Obter contagem e página em uma execução só. Definir
  `statement_timeout` na conexão da API.
- **Aceite:** `/inbox` p95 ≤ 1,5s com 25 mil vagas; query cancelada no banco quando passa do
  timeout.
- **Teste:** os testes de `tests/backend/dashboard/test_queries.py` continuam passando sem
  alteração de expectativa; teste de que a tabela acompanha uma nova avaliação e uma troca de
  perfil.
- **Esforço / risco:** G / médio. Fazer depois do F50-07, que muda a definição de "avaliação
  atual".
- **Depende de:** F50-07.

### F50-11 — Embeddings

- **Problema:** P8.
- **Mudança:** descobrir por que `embed_opportunities` não está no agendador desde
  2026-09-25 e decidir (Q4) se volta. Se voltar, gerar embeddings só para as áreas-alvo.
- **Aceite:** decisão registrada; se ligado, ≥ 95% das vagas das áreas-alvo com embedding.
- **Esforço / risco:** P para investigar; o resto depende da Q4.
- **Decisão (2026-10-05):** o job não parou por falha. Ele foi removido de propósito no
  commit `9f54964` (F20-05), porque o Groq não oferece modelo de embedding
  ([SPEC 43 §9](43-spec-llm-cloud-e-consolidacao.md)). A tabela `opportunity_embedding` e a
  extensão pgvector ficaram. Q4 respondida: embeddings continuam desligados. Voltar exige um
  provedor de embedding aprovado e um adapter novo.

### F50-12 — Pendências de dados

- **Problema:** P8.
- **Mudança:** três itens independentes.
  1. Hacker News: comentário sem empresa ou cargo identificável vira item ignorado, não
     inválido, e a execução termina `SUCCEEDED`.
  2. Duplicatas `title_location_window`: medir a taxa de acerto nas 107 pendentes e decidir se
     a regra pode confirmar sozinha acima de um limiar.
  3. `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`: amostrar 50 das 4.809 e decidir se é mudança
     real de vaga ou efeito de recoleta.
- **Aceite:** Hacker News sem `PARTIAL` recorrente; decisão registrada para os outros dois.
- **Esforço / risco:** P cada / baixo.

---

## 4. Ordem de execução

| Fase | Cards | Por quê |
|---|---|---|
| 1. Medir e cortar ruído | F50-01, F50-04, F50-12 (item 1) | Barato, e reduz o volume que as fases seguintes processam. |
| 2. Classificar | F50-02, F50-05, F50-03 | É o que destrava a elegibilidade. F50-05 e F50-02 invalidam avaliações; fazer juntos para reavaliar uma vez só. |
| 3. Decidir | F50-06 | Só faz sentido com os campos preenchidos. |
| 4. Custo | F50-07, F50-08, F50-09, F50-10 | Reduz escrita diária, tokens e tempo de leitura. |
| 5. Resto | F50-11, F50-12 (itens 2 e 3) | Dependem de decisão. |

Depois de cada fase, repetir as consultas do §2 e atualizar a tabela do §1.

---

## 5. Riscos

- **Reavaliação em massa.** F50-02, F50-05, F50-06 e F50-09 invalidam avaliações ou análises.
  Agrupar as mudanças de taxonomia e de regras em uma única troca de versão evita três
  reavaliações do catálogo.
- **Cota de IA.** Cada invalidação de cache de análise custa até um dia de cota para as
  vagas `HIGH_PRIORITY` e `RECOMMENDED`. Com o perfil real são ~730 vagas nesses vereditos
  (medição parcial), contra ~100 análises por dia.
- **Perda de vagas por filtro.** F50-04 descarta na coleta. `UNKNOWN` nunca é descartado, e o
  aceite compara com uma execução sem filtro.
- **Banco recuperado.** O `spec46full` usa um volume recuperado. Testes de integração só
  rodam em banco dedicado terminado em `_test` (guarda em `tests/backend/conftest.py`).

---

## 6. Perguntas abertas

- **Q1.** O detalhe de vaga do Workday está coberto pela revisão de termos das 15 fontes?
  Recomendação: revisar por fonte antes do F50-03; sem revisão, a fonte fica só com a
  listagem.
- **Q2.** Qual piso de vagas nas áreas-alvo liga o filtro de coleta? Recomendação: 30%,
  medido nas três últimas execuções completas.
- **Q3.** Critério sem dado de origem deve sair da elegibilidade (`NOT_APPLICABLE`)?
  Recomendação: sim para fuso e autorização de trabalho; país continua bloqueando quando
  desconhecido só se o perfil marcar `sponsorship_required`.
- **Q4.** Embeddings voltam? Recomendação: só se F50-05 não levar `TECHNOLOGY_FIT` à meta;
  hoje nenhuma decisão de matching depende deles.
- **Q5.** O perfil ativo declara `SOFTWARE_ENGINEERING` e `DATA` como áreas-alvo e só
  contrato `full-time`. Confirmar, porque F50-04 e a fila de análise passam a depender disso.
