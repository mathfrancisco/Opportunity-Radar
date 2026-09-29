# SPEC — Mais vagas úteis: funil medido, problemas e cards F48

- **Status:** Planejada; nenhuma correção abaixo está feita. Documento de diagnóstico e
  desenho, sem mudança de código, configuração ou teste. **Todas as perguntas abertas foram
  decididas em 2026-09-29** (§9): o usuário delegou a escolha do melhor caminho para o objetivo
  principal (mais vagas úteis e relevantes, dentro dos limites legais e de termos de uso).
- **Data:** 2026-09-29
- **Base verificada:** branch `spec-46-redesign-ui` (`844aafd`) e o banco da stack real em
  execução, lido só com `SELECT` (nada foi escrito, reiniciado ou parado). Snapshot do banco em
  **2026-09-29 ~19:37Z**; o banco muda a cada minuto (avaliação e normalização ainda
  rodavam), então contagens de matching são de um instante.
- **Escopo:** aumentar o número de vagas **úteis, relevantes, novas, sem repetição, bem
  classificadas e bem ordenadas** que chegam ao usuário, dentro dos limites de termos de uso.
  Parte de [`47-arquitetura-atual.md`](47-arquitetura-atual.md) (§3 "Como melhorar" e §7) e de
  [`44-roadmap-fase-20/validacao-pendente.md`](44-roadmap-fase-20/validacao-pendente.md) §7,
  confere cada afirmação no código e no banco, e acha o que os dois documentos não viram.
- **Convenções:** referências `caminho:linha` valem para `844aafd`. O que é **inferido**
  (não observado no código nem medido) vem marcado *(inferido)*. Números do banco vêm de
  consultas descritas no §2 e §3. Escalas de impacto, esforço e risco como no §7 do doc 47.
- **Documentos relacionados:** [Arquitetura atual (47)](47-arquitetura-atual.md),
  [SPEC 45 — startups](45-spec-descoberta-startups.md),
  [SPEC 46 — UI](46-spec-redesign-ui.md), [Fase 20](44-roadmap-fase-20/README.md),
  [runbook](30-runbook.md).

---

## 1. Objetivo e métrica

### 1.1 North-star

> **Vagas úteis novas por dia, visíveis no filtro padrão do Inbox.**

Uma vaga conta como **útil visível** quando, ao mesmo tempo:

1. está aberta (`lifecycle_status <> 'CLOSED'`, `duplicate_of IS NULL`);
2. aparece na consulta padrão do Inbox (`only_recent=true`, áreas-alvo do perfil ativo;
   `presentation/http/dashboard.py:503-512`, `dashboard/queries.py:545`);
3. não é `INELIGIBLE` para o perfil ativo e o país permitido é desconhecido, `BR` ou `ANY`;
4. está numa área-alvo do perfil (`target_role_families`); enquanto o perfil não tiver áreas
   (hoje não tem, ver V06), usa-se o **proxy técnico** `SOFTWARE_ENGINEERING, DATA,
   INFRASTRUCTURE, SECURITY`, que a decisão 1 do §9 grava como áreas-alvo iniciais do perfil
   (F48-13), de modo que proxy e perfil passam a coincidir;
5. conta **uma vez** por `(empresa normalizada, título normalizado)`, para que 100 cidades da
   mesma vaga não valham 100.

"Nova" = `opportunity.created_at` nas últimas 24 h (ou na janela medida). O estoque
(mesmas condições, sem "nova") é a métrica irmã.

**Linha de base (2026-09-29):** estoque útil visível **1.746** (proxy técnico, deduplicado; §2).
**Novas por dia: sem linha de base confiável.** Em 2026-09-29 a importação de 120 fontes criou
10.589 oportunidades de uma vez (10.092 na hora 18Z); as 26,6/dia do rebuild (doc 44,
`rebuild-stack-real-2026-09-29.md`) são de antes disso. A linha de base real só existe depois de
7 dias de agenda estável e de F48-06 (que mede o funil pelo `doctor`).

### 1.2 Métricas-guarda (não podem piorar para subir a north-star)

| Guarda | Por quê | Hoje |
| --- | --- | --- |
| Fontes elegíveis avaliadas por passada / elegíveis | vaga que nunca é coletada não conta | 90/136 (66 %), V01 |
| Fontes habilitadas com coleta bem-sucedida em ≤ 2× a cadência | frescor | não medido; buraco de ~9 h em 09-29 |
| Itens `FAILED` na normalização / itens coletados | vaga perdida | 99/12.536 (0,8 %); Remotive 35/35 |
| Repetição na lista padrão (excedente empresa+título / visíveis) | ruído reduz o valor de cada vaga | 25,7 % do acervo (2.893) |
| `seniority = UNKNOWN`, `work_mode = UNKNOWN`, país desconhecido | vaga bem classificada | 50,7 %, 53 %, 90 % |
| Vagas com veredito diferente de `REVIEW_REQUIRED`/`INELIGIBLE` | ranking existe | **0 de 5.187 avaliadas** |
| Falsos fechamentos (`CLOSED` reaberto depois) | vaga real escondida | não medido |
| `AI_FAILED` por quota / tentativas de análise | custo e fila de IA | 2.008 em 3 dias |
| Hosts proibidos tocados (Gupy, Wellfound, YC/WaaS, Careerflow, Crossover, Braintrust, Landing.jobs) | limite legal | 0 (manter) |

---

## 2. Funil medido

Consultas `SELECT` na stack real (`docker compose -p opportunity-radar`, banco `postgres`),
instante ~19:37Z de 2026-09-29. O acervo saltou de 686 para **11.267 oportunidades** depois da
importação de 120 fontes às 18:41Z. Releitura às 20:04Z do mesmo dia: 11.267 oportunidades,
147 fontes definidas (137 habilitadas, 136 não `manual`), 265 empresas, 338 `company_source`,
12.536 `raw_item`, `seniority = UNKNOWN` 5.711, JUNIOR+INTERN 223. O README e o §5 do doc 47
foram atualizados para este snapshot (eles citavam 686, valor de antes da importação).

### 2.1 Do cadastro à Inbox

| # | Etapa | Quantidade | Perda na etapa | Observação |
| --- | --- | --- | --- | --- |
| 1 | Fontes habilitadas e não `manual` | 136 | | 147 definidas |
| 2 | ...que o job de coleta enxerga | 90 | **46 fora (34 %)** | `worker.py:433`; 38 nunca coletadas (V01) |
| 3 | `raw_item` coletados | 12.536 | | 202 execuções agendadas: 197 `SUCCEEDED`, 2 `PARTIAL`, 3 `FAILED` (fontes de teste) |
| 4 | Normalizados com oportunidade | 12.437 | 99 `FAILED` (0,8 %) | 35 Remotive (`published_at` sem fuso), 61 HN sem título, 3 manuais (V02) |
| 5 | Oportunidades | 11.267 | | 11.427 ocorrências |
| 6 | Abertas (não `CLOSED`) | 11.234 | 33 | fechamento só com run completa (V14) |
| 7 | Sem repetir empresa+título | 8.374 grupos | **2.893 excedentes (25,7 %)** | Bluelight Consulting: 1.420 vagas, 18 títulos (V11) |
| 8 | No filtro padrão (recência 14 dias) | 6.998 | **4.236 escondidas (37,7 % das abertas)** | 5.802 delas "recentes" só por `first_seen_at` (V13) |
| 9 | Avaliadas pelo matching (`match_assessment`) | 5.187 de 11.267 | 6.080 na fila | avaliação de 50/passada; fila esvazia em poucas horas (inferido) |
| 10 | Veredito `HIGH_PRIORITY`/`RECOMMENDED`/`WATCHLIST`/`LOW_MATCH` | **0** | **100 %** | todas `REVIEW_REQUIRED` (4.442) ou `INELIGIBLE` (745, modo de trabalho) (V04) |
| 11 | Análise de IA concluída | 451 de 2.604 tentativas | 2.021 `AI_FAILED` | 2.008 por `QUOTA_EXHAUSTED` (V17) |

Pilha do proxy de "útil visível" (abertas, condições cumulativas):

| Condição acumulada | Vagas |
| --- | --- |
| Abertas | 11.234 |
| + filtro padrão de recência | 6.998 |
| + `work_mode` remoto ou desconhecido | 6.209 |
| + país desconhecido, `BR` ou `ANY` | 5.860 |
| + área técnica (proxy) | 2.083 |
| + uma por empresa+título | **1.746** |

Sem a recência, o mesmo recorte técnico tem **3.905**; a recência esconde **1.822** (47 %), todas
com `published_at` preenchido e ainda vistas na fonte nas últimas 24 h (4.234 de 4.338
ocorrências antigas foram revistas em 24 h).

### 2.2 Maiores quedas (ordem de tamanho)

1. **Ranking inexistente:** 100 % das avaliadas viram `REVIEW_REQUIRED` ou `INELIGIBLE`.
   A ordenação real é só empresa > score cru (V04, V05).
2. **Áreas irrelevantes:** o perfil não tem áreas-alvo, então o Inbox mostra tudo (SALES 1.765,
   OPERATIONS 812, LEGAL 162...); só 2.083 de 6.998 visíveis são técnicas (V06).
3. **Fontes fora do relógio:** ~5,5 mil vagas estimadas ainda não coletadas (V01).
4. **Repetição:** 25,7 % do acervo (V11).
5. **Recência:** 4.236 abertas escondidas e um penhasco em 2026-10-13 (V13).
6. **Remotive:** 0 vagas do agregador remoto (V02).

---

## 3. Problemas priorizados

Impacto = efeito em **vagas úteis** (ou em confiança do funil). `V` = este documento; `P` =
ID do doc 47, quando existe. Ordem = prioridade sugerida.

| ID | Problema | Evidência (resumo) | Impacto | Esforço | Risco | Ref. 47 |
| --- | --- | --- | --- | --- | --- | --- |
| V01 | Job de coleta lê só as 100 primeiras fontes por nome | 46 elegíveis fora, 38 nunca coletadas, ~5,5 mil vagas (inferido); inclui Remotive | Alto | A | Baixo | P0-1 |
| V02 | Remotive: 100 % dos itens `FAILED`; falha nunca é reprocessada | 35/35 `published_at` sem fuso; 0 oportunidades Remotive | Alto | A | Baixo | novo |
| V03 | Contrato do perfil (`full-time`) nunca casa com `FULL_TIME` | `CONTRACT_COMPATIBLE = UNKNOWN` em 100 % | Médio | A | Baixo | novo |
| V04 | Veredito morto: `GEOGRAPHY_CONTRACT_FIT` exige revisão quando qualquer dado falta | 0 vereditos úteis; só 3,4 % das abertas escapariam com V03 sozinho | Alto | M | Médio | P1-7 (parcial) |
| V05 | "Prioridade da empresa" mede maturidade da pesquisa, não interesse | 65 % das vagas em empresa `low`; ordem padrão põe empresa antes do score | Alto | A | Médio | novo |
| V06 | Perfil quase vazio: 1 skill, sem áreas, títulos ou senioridade | `TECHNOLOGY_FIT` conhecido em 6 %; Inbox sem recorte de área | Alto | A (dados) / M (UI) | Baixo | P1-7 (parcial) |
| V07 | Fatores sem avaliador: `DOMAIN_EXPERIENCE`, `SENIORITY_SCOPE`, `TIMEZONE`, `CONTRACT_COMPENSATION` | 4 fatores = 35 % do peso sempre `UNKNOWN` (0,5) | Alto | M | Médio | P1-7 |
| V08 | Classificação sem olhar a descrição: senioridade `UNKNOWN` 50,7 %, `work_mode` 53 %, país 90 % | `domain.py:966`; 47 % dos `UNKNOWN` têm "N anos" na descrição | Alto | M | Médio | P0-2 |
| V09 | Workday: Tavily falha em 100 % e queima créditos, requisições e a coleta | 724/724 falhas; Adobe cortada em 235 itens; 718 vagas sem descrição | Alto | A | Baixo | P2-7 (corrige) |
| V10 | Orçamento de host por `source_type` | `workday` 518 requisições na janela, teto 200; 15 tenants | Médio | A | Baixo | P1-3 |
| V11 | Repetição empresa+título; `duplicate_candidate` vazio | 2.893 excedentes; 0 linhas em `duplicate_candidate` | Alto | M | Médio | P3-4 (amplia) |
| V12 | Mudança de identidade não atualiza a oportunidade (`REVIEW`) | 448 `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`; explica 4 → 185 | Médio | M | Médio | P1-6 (explica) |
| V13 | Recência: base estimada, penhasco e vagas vivas escondidas | 5.802 "recentes" por `first_seen_at`; Greenhouse nunca tem `published_at` | Alto | M | Médio | P2-6 |
| V14 | Fechamento: fecha por uma fonte só; `CLOSED` no Inbox padrão; fontes fora do relógio nunca fecham | 123 oportunidades multi-ocorrência; 33 `CLOSED` visíveis | Médio | A | Baixo | novo |
| V15 | Empresas sem vínculo | 63 fontes sem `company_source`; 1.026 vagas sem empresa; 0 evidências de startup | Médio | M | Médio | P2-3 |
| V16 | Buraco de coleta sem alarme, sem bytes por run | slots 03Z, 06Z e 09Z de 09-29 sem coleta | Médio | A | Baixo | P1-1, P1-5 |
| V17 | Sonda de quota da IA reserva 0 tokens; fila gasta IA em tudo | 2.008 `AI_FAILED`, tentativas queimadas | Médio | A | Baixo | P0-3 |
| V18 | Compose não repassa variáveis; duas variáveis mortas | `compose.yaml:39-40` | Baixo | A | Baixo | P2-5 |
| V19 | Reavaliação diária de tudo e crescimento do banco | 11.267 × 9 linhas/dia (~100 mil/dia; inferido) | Médio | M | Médio | P1-4 |
| V20 | Expansão de fontes e ATS | ver §4.20 | Alto (longo prazo) | M–B | Médio (termos) | novo |

---

## 4. Design da correção de cada problema

### 4.1 V01 — Toda fonte elegível entra no relógio

**Verificado.** `collect_enabled_sources` chama `service.list_sources(offset=0, limit=100)`
(`worker.py:433`), que faz `ORDER BY name` com `OFFSET/LIMIT` (`acquisition/repository.py:58-62`) e
descarta o resto em silêncio; o `if not source.enabled or source.source_type == "manual"`
(`worker.py:436`) só filtra depois do corte. Hoje há 147 definições; as posições 101-147
(alfabeticamente "Proposed Tryjeeves..." até "n8n jobs") têm **46 elegíveis**: 17 Ashby, 10
Greenhouse, 6 Workable, 6 Lever, 5 Workday, 1 Teamtailor e **`Remotive remote jobs`**. Destas,
**38 nunca foram coletadas**; as 8 que já tinham coleta (Render, RevenueCat, Spotify, Supabase,
Trigger.dev, WorkOS, n8n, Remotive) pararam no último ciclo antes da importação (15:00Z e 12:11Z) e
não rodaram mais. A cada fonte nova cujo nome caia antes de "P", mais uma fonte sai do relógio.
Estimativa de vagas fora: 5 Workday × 364 + 10 Greenhouse × 158 + 5 Lever × 204 + 11 Ashby × 70 +
6 Workable × 42 + 1 Teamtailor × 65 ≈ **5,5 mil** *(inferido pela média de itens por tipo nas runs
agendadas)*. As fontes com "0 6 * * *" (Workday) ainda não venceram desde a importação, então as
8 elegíveis sem coleta entre as 100 primeiras são esperadas.

**Correção.** Método de repositório `list_collectable_sources()` = `enabled AND source_type <> 'manual'`,
sem limite, ordenado por `priority` da empresa e depois por `last_started_at NULLS FIRST`
(fonte nunca coletada primeiro, para que a fila não fique presa atrás das lentas). O worker
usa esse método. `list_sources(offset, limit)` continua para a API paginada.

**Efeito esperado:** até ~5,5 mil vagas novas na próxima passada agendada (parte Workday sem
descrição até V09).

### 4.2 V02 — Remotive volta a produzir vagas

**Verificado.** `RemotiveCollector._published_at` faz `datetime.fromisoformat(value.replace("Z",
"+00:00"))` (`acquisition/remotive.py:344-359`). A API entrega `publication_date` sem fuso
*(inferido do resultado: o datetime volta ingênuo)*; o normalizador rejeita datas sem fuso
(`opportunities/service.py:856`, "collected_item_v1 published_at must include a timezone").
Resultado: 35 `raw_item` (19 identidades), 35 `normalization_result` `FAILED`, **0**
oportunidades Remotive no banco. `pending_raw_item_ids` só devolve item sem resultado da versão
atual, então mesmo depois de corrigir o coletor os 35 `FAILED` não são reprocessados sozinhos.

**Correção.** (a) O coletor atribui UTC à data ingênua (conferir a documentação da API antes
de assumir UTC; se não for UTC, gravar `published_at = None` em vez de inventar fuso) e o
normalizador aceita `published_at` ingênuo como `None` com aviso, em vez de reprovar o item
inteiro. (b) Reprocessar os `FAILED` cuja causa foi corrigida: script `backfill_failed_normalizations`
com `--dry-run` (apaga só linhas `FAILED` de `INVALID_COLLECTED_ITEM_V1` dos itens afetados; o
`normalize_pending` refaz). (c) HN: 61 comentários sem título viram "ignorado" (`skipped`), não
`FAILED` (mesma família de F20-75).

### 4.3 V03 — Contrato do perfil casa com o enum

**Verificado.** `_known_contracts` chama `_optional_enum(ContractType, value)`, que faz
`value.strip().upper()` (`matching/service.py:1018-1042`). O perfil guarda `full-time`
(`profile.employment_preference.contracts = {full-time}`), que vira `FULL-TIME` e falha contra
`FULL_TIME`; `accepted_contract_types` fica vazio e `CONTRACT_COMPATIBLE` é `UNKNOWN` nas 5.187
avaliações, embora 4.147 oportunidades abertas tenham contrato conhecido.

**Correção.** Normalizar `-` e espaço para `_` em `_optional_enum` (ou gravar o valor
canônico no perfil e migrar). Teste com `full-time`, `part-time`, `internship`.

### 4.4 V04 — O veredito volta a existir

**Verificado.** `DEFAULT_FACTORS` dá 20 % a `GEOGRAPHY_CONTRACT_FIT` com política
`REQUIRE_REVIEW` (`matching/domain.py:283-290`); o fator vira `UNKNOWN` se qualquer um entre
modo de trabalho, país, autorização, fuso ou contrato for desconhecido (`domain.py:576-600`) e
`review_required` força `REVIEW_REQUIRED` (`domain.py:318-321`, `_verdict` em `:804-820`).
O snapshot da oportunidade **nunca preenche** `allowed_countries`, `work_authorization`,
`timezone_overlap_hours` e `required_timezone_overlap_hours` (`matching/service.py:474-509`),
embora `opportunity.allowed_countries` exista para 996 vagas; o do perfil nunca preenche
`accepted_seniorities` (`service.py:512-545`). Fuso e autorização são **sempre**
desconhecidos hoje. Consequência: das 5.187 avaliadas, 4.442 são `REVIEW_REQUIRED`, 745
`INELIGIBLE` (modo de trabalho) e **nenhuma** tem outro veredito; os scores ficam entre 35 e 72,
ou seja, os cortes 80/65/45 nunca são exercidos.

Simulação com dados reais: mesmo corrigindo V03, só **383 de 11.234** abertas (3,4 %) têm
modo, contrato e país conhecidos ao mesmo tempo.

**Correção (`matching-v2`).**

1. O snapshot passa `allowed_countries` (já calculado no normalizador, `allowed_countries_version`)
   e deixa fuso/autorização como "não coletados" (não como "desconhecidos que exigem revisão").
2. `GEOGRAPHY_CONTRACT_FIT` só considera as dimensões que o sistema **sabe** preencher (modo,
   país, contrato). Dimensão desconhecida entra como neutra (0,5, `NEUTRAL`) e **reduz a
   confiança**, sem forçar `REVIEW_REQUIRED`. `REQUIRE_REVIEW` fica só para **conflito**
   (`compensation_conflict`, evidência contraditória).
3. Reponderar os fatores sem avaliador (V07) e recalibrar 80/65/45 sobre a distribuição real
   (P2-9), com o teste de regressão dos 50 casos de `prompts/opportunity_analysis/eval/cases/`.
4. Reprocessar (avaliação nova com `rules_version = matching-v2`, o histórico fica).

### 4.5 V05 — Prioridade de empresa deixa de ser "maturidade da pesquisa"

**Verificado.** `ResearchRow.source_priority` devolve `high` se a situação contém "api json",
`normal` se "ats identificado", senão `low` (`scripts/import_research_catalog.py:231-237`). Assim
7.265 das 11.267 vagas (64,5 %) pertencem a empresas `low` (OpenAI, Anthropic, Databricks,
Datadog, Cloudflare, Stripe, DoorDash...), 2.747 a `normal`, 229 a `high`, 1.026 sem empresa. A
ordem padrão é `[priority desc, score desc, published_at desc]`
(`dashboard/queries.py:663-675`), então **uma vaga `normal` inelegível ou fraca aparece antes da
melhor vaga de uma empresa `low`**. Além disso `COMPANY_PRIORITY` vale 15 % do score e a agenda
de coleta por prioridade (`scheduling.py:178-182`) reusa o mesmo campo (`low` = semanal).

**Correção.** Separar dois conceitos: `research_confidence` (o que o catálogo sabe; uso
operacional) e `priority` (interesse do usuário; entra no score e na ordem). Importações novas
gravam `priority = normal` por padrão; um script `--dry-run` reclassifica as `low` **que só são
`low` por maturidade**, sem tocar as que o usuário editou (`updated_at` > importação). A ordem
padrão do Inbox passa a `[score desc, published_at desc]` com prioridade como fator do score.

### 4.6 V06 — Perfil que permite ranquear

**Verificado.** O perfil ativo (`60c45fa0...`) tem 1 skill (`python`, `advanced`), 1
experiência, `target_role_families = {}`, `target_titles = {}`, modo `remote`, contrato
`full-time`, país `BR`. Consequências: o Inbox não recorta área (`presentation/http/dashboard.py:508-512`
só recorta quando há áreas), `TECHNOLOGY_FIT` é conhecido em 277 de 4.537 fatores e vale 0,11 na
média, e o Remotive não tem palavras-chave úteis (`profile/keywords.py`).

**Correção.** (a) Dado, não código (decisão 1, §9): gravar como áreas-alvo iniciais o proxy
técnico (`SOFTWARE_ENGINEERING, DATA, INFRASTRUCTURE, SECURITY`) por script com `--dry-run`, sem
sobrescrever área que o usuário já tenha editado; skills e títulos-alvo não são inventados: o
usuário os completa pela tela de perfil, e o aviso do item (b) lembra disso. (b) Código:
preferência de senioridade no perfil (`accepted_seniorities` no snapshot, padrão
INTERN/JUNIOR/MID/UNKNOWN como o F20-72 assume, decisão 2) e aviso na tela de perfil quando
"áreas-alvo" ou skills estão vazias ("o Inbox não filtra por área").

### 4.7 V07 — Avaliadores dos fatores mortos

**Verificado.** `DOMAIN_EXPERIENCE` devolve `UNKNOWN` sempre (`matching/domain.py:623-629`);
`SENIORITY_SCOPE` usa `_seniority_filter`, que é `UNKNOWN` sem `accepted_seniorities`
(`domain.py:423-438`); `TIMEZONE` depende de campos que ninguém preenche;
`CONTRACT_COMPENSATION` depende de V03 e de remuneração comparável (rara). Medido nas 4.537
linhas de fator mais recentes: os quatro fatores são `UNKNOWN` em 100 % (0,5 cru) e somam **35 %**
do peso; `GEOGRAPHY_CONTRACT_FIT` `UNKNOWN` em 4.113 de 4.537.

**Correção.** `DOMAIN_EXPERIENCE` = interseção entre `opportunity.role_family` e as famílias das
experiências/projetos do perfil (dados existem: `profile.experience`, `profile.project`);
`SENIORITY_SCOPE` após V06(b); `TIMEZONE` e `CONTRACT_COMPENSATION` saem do denominador
(`EXCLUDE_AND_RENORMALIZE`) enquanto não houver dado, em vez de valer 0,5. Peso redistribuído
em `matching-v2` (F48-12).

### 4.8 V08 — Classificar pelo conteúdo

**Verificado.** `seniority_classification` chama `infer_seniority(title, None, {})`
(`opportunities/domain.py:966`): a descrição nunca entra, mesmo existindo para 93 % das vagas
(0 vagas sem descrição em Greenhouse/Ashby/Lever/Teamtailor; 718 sem, todas Workday).
`UNKNOWN` = **5.711 de 11.267 (50,7 %)**; entre eles, **2.710 (47 %)** contêm um padrão do tipo
"N years/anos" e 168 contêm "entry-level/junior/estágio/no experience" *(regex simples, sem
precisão medida)*. `MID` é 0,9 % (96) e `JUNIOR` 0,3 % (36): o vocabulário de título quase não
produz esses valores. `work_mode` `UNKNOWN`: 6.006 (53 %); país permitido conhecido: 996 (8,8 %).

**Correção.** Extração determinística com evidência citada, versionada (`seniority-v4`,
`work-mode-v7`, `allowed-countries-v2`), na ordem: campo estruturado do coletor > título >
descrição (faixa de anos → `JUNIOR` 0-2, `MID` 3-5, `SENIOR` 5+, com texto de evidência).
Primeiro medir precisão contra o gabarito (F20-23: 30 vagas rotuladas; ampliar para ≥ 200 com
`scripts/sample_*`), depois gravar. Sugestões de IA só para o resíduo e com aceite humano
(F20-76).

### 4.9 V09 — Workday sem Tavily

**Verificado.** Todo item sem descrição passa por `_fill_missing_description`
(`acquisition/service.py:1292-1339`), que chama a extração da Tavily **uma vez por item**
(`service.py:1056`), com teto de 100 créditos por run (`service.py:1025`,
`TAVILY_CREDIT_BUDGET_PER_RUN` em `compose.yaml:35`). O Workday não traz descrição
(`workday.py`, módulo docstring), então cada vaga vira uma chamada. Em `tavily_extract_cache`:
`aig.wd1.myworkdayjobs.com` 492 falhas, `adobe.wd5.myworkdayjobs.com` 232 falhas, **0
sucessos** ("Failed to fetch url"; páginas Workday são JS). Efeitos medidos:

- Adobe: 100/100 créditos gastos, 0 descrições, run cortada em 235 itens (`PARTIAL`,
  `CREDIT_BUDGET_EXCEEDED`); o resto do board não foi lido.
- AIG: 518 requisições para 492 itens (492 chamadas Tavily + 26 páginas); Adobe: 244 = 232 + 12
  páginas. O contador `http_requests` da run (e o orçamento de host, `service.py:1232`) soma
  **as chamadas Tavily junto** com as do Workday, então o "orçamento do Workday" está
  consumido por extração que nunca funciona.
- 718 vagas Workday sem descrição, logo sem skills nem senioridade por conteúdo.
- A cobrança em falha é inconsistente (Adobe cobrou 100 créditos por falhas; AIG, 0)
  *(não investigado)*.

**Correção.** (1) Configuração `extraction_skip_source_types` (padrão `workday`) e, mais geral,
**parar de extrair para um host depois de N falhas seguidas** (registrar em `tavily_extract_cache`
por host). (2) Contar requisições Tavily em contador separado e **não** no orçamento do host
do ATS. (3) Descrição do Workday por endpoint de detalhe público **só após** revisão de termos
própria (card F48-19; `pesquisas/termos-workday.md` já existe para a listagem).

### 4.10 V10 — Orçamento de host por tenant

**Verificado.** `scheduling_state` e `record_host_budget_usage` usam `_host_for_source_type`
(`acquisition/service.py:100-101`, `:864`, `:1233-1239`), que só mapeia 6 tipos; o restante usa o
próprio `source_type` como chave. Já existe `source_host_key` por tenant
(`acquisition/concurrency.py:68-89`), mas só serve ao `HostSerializer`. `host_budget_state` real:
`workday` 518 usadas de teto 200 na janela de 1 h (`scheduling.py:29,35`), com 15 tenants
Workday no mesmo balde; a janela só reabre com 1 h e uma única run pode gastar > 200, então
na prática **uma fonte Workday por hora**. Também `factorial` 146/200 (2 fontes) e
`hacker-news.firebaseio.com` 302/200 (uma run só).

**Correção.** Usar `source_host_key` (tenant) como chave do orçamento persistido, exceto para
os tipos de host compartilhado, onde a chave física continua correta; migrar linhas existentes
(`workday` → `workday:<tenant>:<region>`); registrar o teto por tipo em configuração.

### 4.11 V11 — Repetição e duplicatas

**Verificado.** (a) Empresa+título repetidos: 8.374 grupos, 785 com mais de uma vaga, 2.893
excedentes. O caso dominante é a Bluelight (Lever): **uma vaga por cidade**, cada uma com URL
própria (100 cidades × 18 títulos = 1.420 vagas, 12,6 % do acervo). (b) O finder
`find_title_location_window_candidates` só roda quando `decision == "NEW"`
(`opportunities/service.py:289-293`); o segundo elemento de um par chega como `REVIEW`
(`SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY`, `service.py:231`), então **`duplicate_candidate`
tem 0 linhas** apesar de 17 grupos com mesma empresa, título e local (ex.: AIG "Collections
Supervisor" em Mexico City, duas publicações a 3 dias). (c) Cruzamento entre fontes: nenhuma
oportunidade tem ocorrências em mais de uma fonte hoje (não há sobreposição medida; risco
futuro com Remotive/HN vs. ATS).

**Correção.** (1) Rodar o finder também para `REVIEW` que criou oportunidade nova. (2) **Agrupar
sem fundir:** chave `posting_group` = `(empresa, título normalizado, fonte)`; o Inbox mostra
uma linha com "+N locais" e a busca/contagens contam o grupo uma vez; nada é fundido nem
fechado (a fusão continua só por confirmação humana, F20-26). (3) Métrica-guarda de repetição.

### 4.12 V12 — Mudança de identidade atualiza a oportunidade

**Verificado.** A impressão digital inclui **modo de trabalho, tipo de contrato, local e dia de
publicação** (`opportunities/domain.py:1062-1092`). Quando a mesma `external_id` chega com
impressão diferente, o normalizador grava `REVIEW_REQUIRED`
(`EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED`, `service.py:186-199`) e **não** chama
`_refresh_opportunity` (só o ramo `fingerprint ==` o faz, `service.py:191-195`): os campos
derivados (modo de trabalho, senioridade, família, skills) ficam como estavam. É o mecanismo
do salto **4 → 185** do v6: a regra de `work_mode` do `13d6605` mudou o campo que entra na
impressão, e as 185 (176 Nubank) ficaram com o valor v5. Hoje são **448** (257 Nubank, 186
CI&T, 5 Firecrawl). O mesmo acontece quando uma empresa edita local ou título de uma vaga viva.

Os demais `REVIEW_REQUIRED` (3.337 no v6) **não são vagas perdidas**: todas têm oportunidade
(`with_opp = 3.337`); 2.878 são `SAME_COMPANY_AND_TITLE_DIFFERENT_IDENTITY` (V11) e 11
`CONFLICTING_COMPENSATION_EVIDENCE`. Os 99 `FAILED` são determinísticos: 64 sem título (61 HN, 3
manuais), 35 Remotive (V02); os "38 fixos" do v5/v6 eram 35 Remotive + 3 manuais.

**Correção.** Quando a `external_id` da fonte é a mesma, ela **é** a identidade: atualizar a
oportunidade (`_refresh_opportunity`), recalcular a impressão e registrar a mudança em
`closure_evidence`/histórico em vez de deixar a linha desatualizada; manter `REVIEW_REQUIRED`
apenas quando **duas oportunidades** diferentes disputam a identidade. Tirar do impressão
digital os campos derivados e instáveis (modo, contrato) ou versionar a impressão
(`fingerprint_version = v2`) para que uma nova versão da regra não gere "mudança de identidade".

### 4.13 V13 — Recência com base explícita

**Verificado.** `_recency_condition` (`dashboard/queries.py:545-565`) usa `published_at` e,
sem ele, `first_seen_at`. A Greenhouse **nunca** traz `published_at`
(`acquisition/greenhouse.py:327-335`): 5.401 vagas (48 % do acervo) e 5.802 no total ficam
"recentes" pela data da coleta. Efeitos: (1) na importação de hoje, 83 % do visível está
visível por `first_seen_at`; (2) **penhasco em 2026-10-13**: se nada novo chegar, essas ~5,8
mil saem do filtro padrão no mesmo dia; (3) com data, 4.236 abertas ficam escondidas embora
estejam vivas (Ashby `publishedAt` original, meses); (4) Greenhouse tem `updated_at` em 100 %
(3.753 dentro de 14 dias), hoje só guardado em `source_updated_at`.

**Correção.** Coluna `recency_basis` (`published`, `updated`, `first_seen`) e regra única
`data_de_referencia = published_at ?? source_updated_at ?? first_seen_at`, mostrada na UI como
"estimada" quando não for `published`. A exceção de programa com prazo continua do F20-61.
**Decidido em 2026-09-29 (decisão 3, §9):** a janela padrão do Inbox passa de 14 para 30 dias
sobre essa data de referência, com as lentes "Novas (14 dias)" e "Abertas na fonte" (vista na
última run completa da sua fonte, sem limite de data).

### 4.14 V14 — Fechamento correto

**Verificado.** `reconcile_run_closures` fecha uma oportunidade quando a ocorrência de **uma
fonte** sumiu de duas runs completas seguidas, sem olhar as outras ocorrências
(`opportunities/service.py:441-458`; `occurrences_missing_from_both_runs`,
`opportunities/repository.py:245-266`); 123 oportunidades têm mais de uma ocorrência (na mesma
fonte hoje, mas o caso multi-fonte é o futuro do dedup). Só run `complete` fecha
(`evaluate_completeness`, `acquisition/domain.py:492-513`); 116 de 202 runs agendadas são
completas, e as 72 Ashby "não completas" são runs sem item (`items_seen = 0`, provavelmente
304; *inferido*). Vagas de fontes que **não rodam** (V01) nunca fecham. O Inbox padrão **não
filtra** `lifecycle_status` (`dashboard/queries.py:567+`; 33 `CLOSED` aparecem, com veredito
`INELIGIBLE`).

**Correção.** Fechar só quando **nenhuma** ocorrência da oportunidade foi vista na última run
completa da sua fonte; excluir `CLOSED` do Inbox padrão (filtro explícito continua). `STALE` e
`DISCOVERED → ACTIVE` não têm transição automática hoje (11.233 `DISCOVERED`); a
transição só importa se a UI passar a distinguir.

### 4.15 V15 — Empresas ligadas

**Verificado.** 63 fontes habilitadas sem `company_source_id` (24 são "Proposed ...");
1.026 oportunidades sem `canonical_company_id` (191 nomes; Adobe 229, Legionhealth 158, EWOR 97);
`company_startup_evidence` tem 0 linhas (o filtro "startup" devolve vazio). Há 40
`company_source` com ATS identificado e **sem** `source_definition`, em parte a mesma empresa
das 63 (Replit, TestGorilla, Seedtag, Accenture...). A propose só cobre Ashby, Lever e
Greenhouse (`acquisition/service.py:358`); Workable, Teamtailor, Factorial e Workday não têm
caminho de proposta.

**Correção.** Script `link_source_companies` (dry-run): para cada fonte sem vínculo, criar
`Company` + `CompanySource` a partir de `configuration.company_name` e ligar; unir com a
empresa existente por `normalized_name`. Estender `propose_company_source` aos outros tipos
com identificador. Depois reexecutar `backfill_startup_evidence.py`.

### 4.16 V16 — Buraco de coleta com alarme

**Verificado.** Runs agendadas por hora (UTC) em 09-29: 00Z (16), depois **12Z (16)**; faltam
03Z, 06Z e 09Z. O fuso do agendador é `America/Sao_Paulo` (`compose.yaml:38`), então os slots são
00, 03, 06, 09, 12... local. O worker atual só está "Up About an hour" (rebuild); o restante do
buraco é anterior. A causa **não está no banco** *(hipótese: host/Docker parado; `worker_job_state`
não guarda histórico)*. O alerta existente (`acquisition/alerts.py`) abre incidente por fonte com
run falha, e **não** cobre "nenhuma run". `source_run` não guarda bytes nem idade da vaga
mais nova.

**Correção.** Checagem no `doctor` e em `/source-health`: "nenhuma run agendada há > 2× a
cadência" por fonte e global; guardar duração e término da passada em `worker_job_state` por
execução (tabela de histórico curta); somar `len(response.content)` no telemetria e gravar
`bytes_received` e `newest_item_age_seconds` em `source_run`.

### 4.17 V17 — Quota da IA e fila

**Verificado.** A sonda reserva `estimated_tokens = 0` (`worker.py:215-226`,
`quota_guard.reserve(adapter.model, 0, ceiling_requests=...)`); `reserve` compara
`tokens + 0` com o teto de tokens do dia (`platform/ai/quota.py:197-246`), então com
169.522 de 170.000 tokens usados a sonda passa e a chamada real falha com `QUOTA_EXHAUSTED`.
`ai_call_record`: 46 (09-26), 43 (09-28), 43 (09-29) falhas de quota; `match_analysis`:
420 + 1.069 + 519 = **2.008** `AI_FAILED` por `QUOTA_EXHAUSTED`, e cada uma conta como
tentativa (limite 3/24 h, `DEFAULT_ANALYSIS_MAX_ATTEMPTS`, `matching/service.py:69-79`). A cota
diária (~170 mil tokens) esgota ~13:27Z. Como todo veredito é `REVIEW_REQUIRED` (V04) e
`REVIEW_REQUIRED` é elegível à análise, a IA é gasta em qualquer vaga.

**Correção.** Sonda com `estimated_tokens = <estimativa do primário>` e, se não houver saldo,
**sair do lote sem gravar `AI_FAILED`**; `pending_analysis_ids` ordenado por score. Após V04,
restringir a fila a `HIGH_PRIORITY/RECOMMENDED/WATCHLIST`.

### 4.18 V18 — Compose

**Verificado.** `compose.yaml` passa `WORKER_ANALYZE_VERDICTS`, `WORKER_*_BATCH_SIZE` e os
interruptores, mas **não** `WORKER_SUGGEST_ENABLED`, `WORKER_SUGGEST_BATCH_SIZE`,
`WORKER_ANALYZE_AGING_SAMPLE_RATIO` (padrão 0,10, `platform/config.py:38`),
`AI_INTERACTIVE_RESERVE_REQUESTS` (padrão 100, `config.py:82`), `AI_CALL_RECORD_RETENTION_DAYS`
e `AI_REASONING_EFFORT_JOB_*`. `WORKER_CONCURRENCY` e `ANALYSIS_CONCURRENCY`
(`compose.yaml:39-40`, `.env.example:14-15`) não são lidas em `src/` nem em `scripts/`.

**Correção.** Repassar as variáveis faltantes com o padrão do `Settings`; remover as duas mortas;
estender o passo `Verify the kill switches reach the worker` do CI a `WORKER_SUGGEST_ENABLED`.

### 4.19 V19 — Reavaliação orientada a mudança

**Verificado.** `evaluate-pending` reavalia toda oportunidade sem avaliação **do dia**
(`worker.py`, job a cada 60 s, lote 50): 11.267 × (1 avaliação + 8 fatores) ≈ 100 mil linhas/dia
*(inferido)*, ~37 milhões de linhas de fator por ano. Design em doc 47 §2 item 1 e P1-4:
reavaliar só com mudança de versão da oportunidade, do perfil, das regras **ou** da faixa de
recência. Sem isso, o banco cresce mais depressa que o número de vagas.

### 4.20 V20 — Expansão de fontes e tipos de ATS

Ordem por custo-benefício (todas dentro de termos; nenhuma fonte proibida):

1. **Fontes já prontas, sem código novo.** V01 (5,5 mil vagas em fontes já habilitadas); os 40
   `company_source` com ATS identificado e sem fonte (§4.15), ligando-os às definições
   existentes e propondo só os realmente sem fonte; 50 empresas `backlog` e 223 links `careers`
   para `discover_sites`/JSON-LD (coletor `jobposting` já homologado).
2. **F20-60 residual.** 13 empresas sem ATS para `discover_sites.py` em ou depois de
   **2026-10-28** (fim do lock de 30 dias), **antes** de `discover_ats.py`, Crossover excluído; 9
   empresas `probe` sem decisão (Mercado Livre, Nuvemshop, FullStack, AgileEngine, Cognizant, TCS,
   Infosys, Terminal, AI/R Avenue Code); não ativar os boards homônimos (`fullstack`, `terminal`,
   `tcs`, `aircompany`). Nuvemshop é `inhire`; AgileEngine tem JSON-LD (`careers-backlog-f20-60`).
3. **Hacker News.** Fonte `0 18 3 * *` (mensal, dia 3, 18Z): a próxima execução é 2026-10-03.
   O "Who is hiring?" é publicado no início do mês; validar que o dia 3 já o inclui e que a
   run captura a thread nova (não a do mês anterior). 175 oportunidades HN existem; 19
   comentários "sem empresa" e 61 sem título viram `skipped` (V02).
4. **Novos tipos de ATS, só depois de revisão de termos** (padrão `pesquisas/termos-*.md`):
   SmartRecruiters (Grupo OLX usa `OLXBrasil`), BambooHR (Lemon.io usa `lemonio`), Recruitee,
   `inhire` (Nuvemshop; ATS brasileiro), Personio/Breezy/Pinpoint. **Todos são hipótese**: a
   existência de API pública e os termos **não foram verificados** nesta rodada. Nenhum
   coletor entra sem (a) termos lidos e registrados, (b) endpoint público documentado, (c)
   probe real de 1 item, (d) teste com fixture, como nos cards F20-27 a F20-31.
5. **Agregadores de vagas remotas com API oficial** (além do Remotive): candidatos a revisar
   termos e atribuição; nenhum é declarado viável aqui. **Decidido (2026-09-29):** entram na
   mesma revisão de termos do F48-19 (mesmo padrão `termos-*.md`, mesmo rito de coletor do
   F48-20); nenhum coletor sem veredito "viável" por escrito.
6. **Lista proibida permanece:** Gupy, Wellfound, YC/Work at a Startup, Careerflow, Crossover,
   Braintrust, Landing.jobs. F48-19 propõe a lista central (P2-1) para que isso seja
   verificado em código, não só em documentos. **Nota sobre Braintrust:** o motivo do card
   F20-56 é a **falta de endpoint estruturado**, não cláusula de termos de uso. Ela **continua
   excluída** (decisão 8, §9), mas o `FORBIDDEN_PLATFORMS` do F48-19 e os demais documentos
   devem registrar esse motivo, sem chamá-la de "proibida por termos".

---

## 5. Fatias (cards F48)

Cada card: escopo pequeno, critério de aceite com teste. Nenhum altera a lista proibida nem
chama serviço externo real no CI (fixtures/`httpx.MockTransport`, padrão da Fase 20).
Validação segue `AGENTS.md`: teste mais estreito primeiro, depois a suíte completa e
`RUN_DATABASE_INTEGRATION=1` uma vez no fim.

### Onda 1 — ganhos rápidos (horas a poucos dias)

**F48-01 — Toda fonte elegível entra no relógio (V01).**
Escopo: `acquisition/repository.py`, `acquisition/service.py`, `worker.py:433`.
Aceite:
- [ ] `collect_enabled_sources` considera `enabled AND source_type <> 'manual'` sem limite.
- [ ] Ordem: fonte nunca coletada primeiro, depois prioridade e nome.
- [ ] `list_sources` paginado da API continua igual.
Teste: em `tests/backend/acquisition/test_collection_job.py`, 101+ (e 150) fontes elegíveis
agendadas; todas avaliadas na passada; uma desabilitada e uma `manual` no meio continuam
ignoradas. Verificação real: depois do deploy, `eligible_never_run` cai de 38 para 0.

**F48-02 — Sonda de quota com tokens e sem `AI_FAILED` (V17).**
Escopo: `worker.py:215-226`, `platform/ai/quota.py`.
Aceite:
- [ ] A sonda reserva a estimativa de tokens do modelo primário.
- [ ] Sem saldo, o lote termina com `skipped_budget` e **nenhuma** linha `AI_FAILED`.
- [ ] Nenhuma tentativa é consumida pelo defer.
Teste: em `tests/backend/matching/test_analysis_queue.py`, contador do dia a 169.900 de 170.000
tokens: 0 chamadas ao provedor, 0 `match_analysis` novos, tentativas iguais; com saldo, chama.

**F48-03 — Remotive volta a produzir vagas (V02).**
Escopo: `acquisition/remotive.py:344-359`, `opportunities/service.py:842-857`, novo
`scripts/backfill_failed_normalizations.py`.
Aceite:
- [ ] `publication_date` sem fuso não reprova o item; o coletor grava `published_at = None`
  (decisão 9, §9: não inventar fuso) e a recência usa a data de referência do F48-16. Só passa
  a UTC se a documentação oficial da Remotive disser UTC, com o link citado no card.
- [ ] `--dry-run` do script lista os 35 itens afetados; execução apaga só `FAILED`
  `INVALID_COLLECTED_ITEM_V1` e o `normalize_pending` cria as oportunidades.
- [ ] HN sem título vira `skipped`.
Teste: fixture Remotive com `"2026-09-29T08:00:00"` gera oportunidade; teste do script com
banco de teste (dry-run não escreve; real reprocessa). Verificação real: oportunidades
Remotive > 0.

**F48-04 — Contrato do perfil casa com o enum (V03).**
Escopo: `matching/service.py:1018-1042`.
Aceite:
- [ ] `full-time`, `part-time`, `internship` e `FULL_TIME` resolvem para o mesmo enum.
- [ ] `CONTRACT_COMPATIBLE` deixa de ser `UNKNOWN` quando ambos os lados têm valor.
Teste: `tests/backend/matching/test_domain.py` e um caso de snapshot de perfil com
`contracts = ["full-time"]`.

**F48-05 — Compose repassa as variáveis e some com as mortas (V18).**
Escopo: `compose.yaml`, `.env.example`, `.github/workflows/pipeline.yml`.
Aceite:
- [ ] `WORKER_SUGGEST_ENABLED`, `WORKER_SUGGEST_BATCH_SIZE`, `WORKER_ANALYZE_AGING_SAMPLE_RATIO`,
  `AI_INTERACTIVE_RESERVE_REQUESTS`, `AI_CALL_RECORD_RETENTION_DAYS` e `AI_REASONING_EFFORT_JOB_*`
  chegam ao worker com o padrão do `Settings`.
- [ ] `WORKER_CONCURRENCY` e `ANALYSIS_CONCURRENCY` removidas.
Teste: passo do CI que sobe o worker com `WORKER_SUGGEST_ENABLED=true` e confere o log de
partida; `docker compose config` sem as variáveis mortas.

### Onda 2 — completude e frescor da coleta

**F48-06 — Funil e north-star no `doctor` (§1, §2).**
Escopo: `scripts/doctor.py`, `dashboard/metrics.py`, endpoint de métricas.
Aceite:
- [ ] Saída com as etapas do §2 e com a north-star (estoque útil e novas/24 h) usando o proxy
  técnico enquanto o perfil não tiver áreas.
- [ ] Guardas do §1.2 no mesmo relatório.
Teste: `tests/backend/dashboard/test_metrics.py` com base semeada (contagens exatas, dedup
por empresa+título, recência por `first_seen_at`).

**F48-07 — Alarme de buraco de coleta e bytes por run (V16).**
Escopo: `operations/`, `acquisition/domain.py` (telemetria), `acquisition/models.py`,
migração `alembic`, `doctor`.
Aceite:
- [ ] `doctor` e `/source-health` avisam quando nenhuma run agendada ocorreu em > 2× a cadência
  (global e por fonte).
- [ ] `source_run.bytes_received` e `newest_item_age_seconds` gravados.
- [ ] Histórico curto de passadas em `worker_job_state` (duração, fontes DUE).
Teste: relógio controlado; migração ida e volta (job `backend-tests`).

**F48-08 — Workday sem Tavily e orçamento por tenant (V09, V10).**
Escopo: `acquisition/service.py:1025-1339`, `acquisition/concurrency.py`,
`acquisition/repository.py`, migração de `host_budget_state`.
Aceite:
- [ ] `extraction_skip_source_types` (padrão `workday`) e parada após N falhas seguidas por host.
- [ ] Chamadas Tavily contadas à parte; não entram em `host_budget_state` do ATS.
- [ ] Chave do orçamento por tenant para Workday/Teamtailor/Factorial/JobPosting.
- [ ] Adobe completa a paginação sem `CREDIT_BUDGET_EXCEEDED`.
Teste: `tests/backend/acquisition/test_workday_collector.py` e `test_host_budget_scheduling.py`
(15 tenants não compartilham balde; run com 500 itens sem uma chamada Tavily).

**F48-09 — Identidade: refresh na mesma `external_id` e finder de duplicatas em `REVIEW` (V12, V11).**
Escopo: `opportunities/service.py:186-199,289-293`, `opportunities/duplicates.py`.
Aceite:
- [ ] Mesma `external_id` com impressão nova atualiza a oportunidade (campos derivados
  refeitos, `version` incrementada) e grava a impressão nova.
- [ ] `REVIEW_REQUIRED` só quando duas oportunidades disputam a identidade.
- [ ] Oportunidade nova criada como `REVIEW` também chama o finder de janela título+local.
- [ ] Script de backfill (`--dry-run`) para as 448 existentes.
Teste: `tests/backend/opportunities/test_service.py` (reprocessar v5→v6 com `work_mode`
diferente atualiza o campo) e `test_duplicates.py` (par AIG "Collections Supervisor" gera
`PENDING`).

**F48-10 — Agrupar a mesma vaga em N locais (V11).**
Escopo: `dashboard/queries.py`, `presentation/http/dashboard.py`, `apps/web` (Inbox).
Aceite:
- [ ] Inbox e contagens mostram um item por `(empresa, título normalizado, fonte)` com "+N
  locais"; a lista dos locais aparece no detalhe.
- [ ] Nada é fundido, fechado ou reescrito.
- [ ] Filtro de fonte, busca e paginação continuam consistentes.
Teste: `tests/backend/dashboard/test_queries.py` (100 cidades → 1 item, total correto,
paginação estável) e teste de componente da Inbox.

**F48-11 — Fechamento correto (V14).**
Escopo: `opportunities/service.py:441-458`, `opportunities/repository.py:245-266`,
`dashboard/queries.py`.
Aceite:
- [ ] Fecha só se nenhuma ocorrência foi vista na última run completa da sua fonte.
- [ ] `CLOSED` fora do Inbox padrão; `lifecycle_status` explícito continua funcionando.
Teste: `tests/backend/opportunities/test_run_closures.py` (duas fontes, uma some, a outra
mantém → não fecha) e `test_queries.py`.

### Onda 3 — ranking e classificação

**F48-12 — `matching-v2` (V04, V07).**
Escopo: `matching/domain.py`, `matching/service.py:474-545`, `RULES_VERSION`.
Aceite:
- [ ] Snapshot passa `allowed_countries`.
- [ ] `GEOGRAPHY_CONTRACT_FIT` considera modo, país e contrato; desconhecido é neutro e
  reduz confiança; `REQUIRE_REVIEW` só em conflito.
- [ ] `DOMAIN_EXPERIENCE` avaliado por família; `TIMEZONE`/`CONTRACT_COMPENSATION`
  renormalizados quando sem dado.
- [ ] Em amostra real reavaliada, ≥ 30 % das vagas elegíveis recebem `RECOMMENDED`,
  `WATCHLIST` ou `HIGH_PRIORITY` *(meta a calibrar com o usuário; o guarda é "diferente de 0")*.
Teste: `tests/backend/matching/test_domain.py` (matriz de conhecimento) e regressão dos 50
casos rotulados (`prompts/opportunity_analysis/eval/cases/`); relatório de distribuição de
veredito antes/depois no evidence file.

**F48-13 — Perfil rankeável (V06).**
Escopo: `profile/domain.py`, `profile/service.py`, `apps/web/src/routes/ProfilePage.tsx`,
migração.
Aceite:
- [ ] Preferência de senioridade no perfil e no snapshot (`accepted_seniorities`); padrão
  INTERN, JUNIOR, MID e UNKNOWN, SENIOR+ "abaixo, não excluído" (decisão 2).
- [ ] Script com `--dry-run` grava `target_role_families` = `SOFTWARE_ENGINEERING, DATA,
  INFRASTRUCTURE, SECURITY` no perfil ativo quando estiver vazio, sem sobrescrever edição do
  usuário (decisão 1); com isso o Inbox passa a recortar por área e o proxy do §1 deixa de ser
  proxy.
- [ ] Aviso na tela do perfil quando áreas-alvo ou skills estão vazias.
- [ ] Perfil sem senioridade **não elimina** INTERN/JUNIOR (mantém o F20-72).
Teste: `tests/backend/profile/`, teste de componente da `ProfilePage`, ponta a ponta "perfil
sem senioridade" no `tests/backend/matching`.

**F48-14 — Prioridade de empresa (V05).**
Escopo: `scripts/import_research_catalog.py:231-237`, `dashboard/queries.py:663-675`,
novo script de reclassificação.
Aceite:
- [ ] Importações gravam `priority = normal`; maturidade vai para campo próprio.
- [ ] Ordem padrão `score desc, published desc`; prioridade só como fator.
- [ ] Reclassificação `--dry-run` não toca empresa editada pelo usuário.
Teste: `tests/backend/test_research_catalog_import.py` e `test_queries.py`.

**F48-15 — Classificação por conteúdo (V08).**
Escopo: `opportunities/domain.py:946-984`, `role_family.py`, regiões.
Aceite:
- [ ] `seniority-v4`, `work-mode-v7`, `allowed-countries-v2` com evidência citada.
- [ ] Precisão ≥ 90 % por regra no gabarito ampliado (≥ 200 vagas) **antes** de gravar.
- [ ] `seniority_unknown_rate` de 50,7 % para ≤ 30 % nas vagas com descrição; nenhum valor
  gravado sem evidência.
Teste: `tests/backend/opportunities/test_domain.py` com tabela de frases reais (PT e EN);
`--dry-run` mede o antes/depois no acervo. Reprocessamento só com backup verificado.

**F48-16 — Recência com base explícita (V13).**
Escopo: `opportunities/domain.py` (`recency_decision`), `dashboard/queries.py:545-565`,
migração (`recency_basis`), `apps/web`.
Aceite:
- [ ] `recency_basis` gravada e mostrada na UI ("estimada" quando não `published`).
- [ ] Regra única em Python e SQL (espelho testado).
- [ ] Janela padrão do Inbox de 30 dias sobre `published_at ?? source_updated_at ?? first_seen_at`
  (decisão 3); lente "Novas (14 dias)" preserva o pedido do F20-61; lente "Abertas na fonte"
  mostra tudo que a última run completa da fonte ainda viu; exceção de programa com prazo mantida.
- [ ] O penhasco de 2026-10-13 não ocorre para vaga com `source_updated_at` recente.
Teste: `tests/backend/opportunities/test_recency_filter.py`, `test_recency_filter_http_integration.py`
e teste de componente. **Não depende mais de decisão do usuário** (decidido em 2026-09-29).
Como muda o padrão do F20-61 (14 dias), o card atualiza o texto e os testes desse card.

### Onda 4 — empresas e expansão

**F48-17 — Vincular empresas e propostas para todos os ATS (V15).**
Escopo: novo `scripts/link_source_companies.py`, `acquisition/service.py:346-390`.
Aceite:
- [ ] `--dry-run` lista as 63 fontes e a empresa que seria criada/ligada.
- [ ] Depois de executar, `enabled` sem vínculo = 0 e `canonical_company_id IS NULL` cai de
  1.026 para o resíduo sem empresa real.
- [ ] `propose_company_source` cobre Workable, Teamtailor, Factorial e Workday.
- [ ] `backfill_startup_evidence.py` grava > 0 linhas.
Teste: `tests/backend/companies/test_company_link.py`, `tests/backend/acquisition/test_tavily_proposals.py`.

**F48-18 — Ativar o pool interno de boards (V20.1).**
Escopo: dados e `scripts/enable_sources.py`; sem código novo de coletor.
Aceite:
- [ ] Os ~40 `company_source` com ATS identificado e sem fonte (decisão 6: podem ser
  ativados) viram propostas e passam pelo probe (`TERMS_REVIEWED=1` só após conferência, como
  hoje). Só depois de F48-01 estar implantado, para não competir por relógio.
- [ ] Nenhum host proibido; nenhuma fonte duplicada de uma já habilitada.
Teste: `tests/backend/test_enable_sources.py`; evidência em `docs/44-roadmap-fase-20/evidencias/`.

**F48-19 — Lista central de plataformas proibidas + revisão de termos de novos ATS (V20.4, P2-1).**
Escopo: novo módulo `acquisition/forbidden.py`, `create_source`, importadores, novos
documentos `docs/pesquisas/termos-<ats>.md`.
Aceite:
- [ ] `FORBIDDEN_PLATFORMS` aplicada em `create_source`, propostas e importadores, com o motivo
  (Gupy, Wellfound, YC/Work at a Startup, Careerflow, Crossover, Braintrust, Landing.jobs).
  Braintrust entra com o motivo "sem endpoint estruturado (F20-56)", não "termos"; segue
  excluída até haver endpoint e revisão de termos próprios (decisão 8).
- [ ] Agregadores remotos com API oficial candidatos à revisão (decisão de §4.20 item 5) têm o
  mesmo documento de termos e veredito.
- [ ] Um documento de termos por candidato (SmartRecruiters, BambooHR, Recruitee, `inhire`, e o
  endpoint de detalhe do Workday) com veredito **viável / não viável / a confirmar**, cláusulas
  citadas e endpoint público documentado.
Teste: `tests/backend/acquisition/test_service.py` (criar fonte para `gupy.io` é recusado).

**F48-20 — Primeiro coletor de ATS aprovado (V20.4).**
Escopo: só para o candidato com veredito **viável** no F48-19; segue o modelo do F20-30
(Workable): coletor, registro, probe, fixture, homologação em board real.
Aceite: os do card de coletor da Fase 20 (probe real, `SUCCEEDED`, dedupe, 304 quando existir).
Teste: `test_<ats>_collector.py` com `httpx.MockTransport`.

**F48-21 — Pendências datadas do F20-60 e do HN (V20.2-20.3).**
Escopo: execução, não código.
Aceite:
- [ ] `discover_sites.py` nas 13 empresas em ou depois de 2026-10-28, antes de `discover_ats.py`.
- [ ] Decisão (`activate`/`no-site`) para as 9 `probe`.
- [ ] Execução HN de 2026-10-03 confere a thread do mês e conta itens novos.
Evidência: arquivo novo em `docs/44-roadmap-fase-20/evidencias/`.

**F48-22 — Reavaliar só com mudança (V19, P1-4).**
Escopo: `matching/service.py`, `worker.py` (`evaluate_pending`).
Aceite:
- [ ] Reavaliação só com mudança de versão da oportunidade, do perfil ou das regras, ou de faixa
  de recência.
- [ ] Linhas/dia de `match_assessment` caem em ordem de grandeza.
Teste: `tests/backend/matching/test_reevaluation.py`, `test_evaluation_queue.py`.

---

## 6. Ordem recomendada

1. **F48-01 e F48-02** (V01, V17): mudança pequena, efeito imediato (cobertura e custo de IA).
2. **F48-03, F48-04, F48-05**: Remotive volta, contrato do perfil casa, compose completo.
   Junto, a **parte de dados do F48-13** (áreas-alvo iniciais no perfil, decisão 1): é um script
   pequeno e é o que faz o Inbox parar de mostrar vendas, jurídico e operações já na onda 1. A
   parte de código do F48-13 (senioridade no perfil, aviso) continua na etapa 6.
3. **F48-06 e F48-07**: medir o funil e alarmar buraco *antes* das mudanças de ranking, para
   que a north-star tenha linha de base.
4. **F48-08 e F48-09**: Workday deixa de queimar Tavily e de travar o orçamento; identidade
   deixa de deixar vaga desatualizada e o dedup passa a funcionar.
5. **F48-10 e F48-11**: agrupamento e fechamento.
6. **F48-13, F48-12, F48-14, F48-15** (nessa ordem: dado do perfil, regras, prioridade,
   conteúdo): ranking útil. F48-12 e F48-15 exigem gabarito e medição antes de gravar.
7. **F48-16** (recência): decisão já tomada (decisão 3); pode entrar junto com F48-10 se o
   escopo couber, e deve sair **antes de 2026-10-13**, data do penhasco de recência.
8. **F48-17, F48-18, F48-19, F48-20, F48-21**: expansão, com a lista central e a revisão de
   termos antes de qualquer coletor novo; F48-21 respeita as datas.
9. **F48-22** quando o banco começar a pesar.

Backup verificado e `--dry-run` obrigatórios antes de F48-03 (script), F48-09 (backfill),
F48-14 e F48-15 (reclassificar/reprocessar). O restore-check do dump `pre-rebuild-2026-09-29`
(doc 47 P0-4) continua pendente e deveria vir antes de qualquer reprocessamento em massa.

---

## 7. Não-objetivos

- Tocar Gupy, Wellfound, YC/Work at a Startup, Careerflow, Crossover, Braintrust ou
  Landing.jobs, ou contornar bloqueio de bot (403/429 de site não é convite a burlar).
- Aumentar volume por ampliar frequência de coleta além dos limites de cada host.
- Fundir ou fechar vaga automaticamente por heurística (F20-26 permanece: fusão só com
  confirmação humana).
- Mudar o resultado de elegibilidade para esconder vaga sem regra explícita e testada.
- Trocar de provedor de IA ou de modelo (F20-22 segue à parte); IA só no resíduo e com aceite.
- Autenticação, multiusuário ou redesenho de UI (SPEC 46 é independente).
- Cobertura "total" de qualquer universo: a promessa é mais vagas úteis e medidas, não todas.

---

## 8. Riscos

| Risco | Efeito | Mitigação |
| --- | --- | --- |
| F48-01 dispara ~46 fontes de uma vez (~5,5 mil vagas) | pico de coleta, normalização, avaliação e Groq | avaliação e normalização já esvaziam em horas; ordem "nunca coletada primeiro"; limitar a passada por tempo se preciso |
| `matching-v2` muda ordem de todo o Inbox | usuário estranha o ranking | manter `matching-v1` no histórico; relatório antes/depois; `RULES_VERSION` novo |
| Reclassificar prioridade (`low` → `normal`) apaga escolha do usuário | perda de curadoria | só empresas não editadas; `--dry-run`; backup |
| Reprocessamento em massa (identidade, conteúdo) | tempestade de avaliação e IA | `version` só muda quando o valor muda; lotes; backup verificado |
| Extração por regex de anos gera senioridade errada | vaga júnior sumir do filtro | precisão ≥ 90 % no gabarito antes de gravar; evidência citada; `UNKNOWN` continua válido |
| Agrupar por N locais esconde uma vaga que só existe numa cidade | vaga real invisível | grupo por `(empresa, título, fonte)` lista locais; busca por local continua |
| Termos de novo ATS mudam | coleta indevida | um documento de termos por ATS, rerevisão a cada 6 meses; nada ativa sem `TERMS_REVIEWED` |
| Janela de 30 dias muda o padrão de 14 dias do F20-61 | Inbox mais cheio | lente "Novas (14 dias)" mantém o pedido original; recorte por área e agrupamento (F48-10) compensam; reversível por configuração |
| Áreas-alvo gravadas por mim no perfil (decisão 1) não refletem o interesse real | vaga boa de outra área some do padrão | só grava se vazio; o usuário edita na tela de perfil; filtro de área continua aberto no Inbox |

---

## 9. Decisões (2026-09-29)

O usuário delegou todas as perguntas abertas e pediu o melhor caminho para o objetivo principal
(maximizar vagas úteis e relevantes, dentro dos limites legais e de termos de uso). Cada decisão
abaixo é registrada, com o motivo; onde a revisão do código e dos dados mudou a recomendação
original, isso está dito.

1. **Perfil-alvo.** Decidido em 2026-09-29: gravar como áreas-alvo iniciais o proxy técnico
   (`SOFTWARE_ENGINEERING, DATA, INFRASTRUCTURE, SECURITY`) no perfil ativo, por script com
   `--dry-run` que só escreve se o campo estiver vazio (F48-13, parte de dados, já na onda 1).
   Skills e títulos-alvo **não** são preenchidos por mim: são fatos pessoais que não devo
   inventar; o aviso da tela de perfil os pede. Motivo: hoje cerca de 70 % dos 6.998 visíveis (só 2.083 são técnicos) são de áreas
   não técnicas (vendas, operações, jurídico) ou sem área útil, e o proxy já é a definição da north-star (§1);
   gravá-lo faz Inbox e métrica coincidirem, é reversível pela UI e não exige esperar o usuário.
   Mudou em relação à recomendação (que esperava o usuário preencher tudo): as áreas não
   dependem mais dele.
2. **Senioridades aceitas.** Decidido em 2026-09-29: INTERN, JUNIOR, MID e UNKNOWN; SENIOR ou
   mais fica "abaixo, não excluído". Motivo: é o que o F20-72 já assume, esconder SENIOR seria
   elegibilidade sem regra explícita (§7) e `UNKNOWN` é 50,7 % do acervo. Vira preferência
   editável no perfil (F48-13).
3. **Janela de recência.** Decidido em 2026-09-29: base `published_at ?? source_updated_at ??
   first_seen_at` (V13) e janela padrão do Inbox de **30 dias**, com lentes "Novas (14 dias)" e
   "Abertas na fonte". Mudou em relação à recomendação (manter 14 dias, decidir 30 depois): os
   dados mostram que 1.822 vagas técnicas (47 %) somem do padrão por recência, todas vistas
   vivas na fonte nas últimas 24 h, e que o penhasco de 2026-10-13 esconderia de uma vez ~5,8 mil.
   14 dias continua disponível como lente, então o pedido do F20-61 não se perde. F48-16 deixa
   de esperar o usuário e deve sair antes de 2026-10-13.
4. **Prioridade de empresa.** Decidido em 2026-09-29: importações gravam `normal`; curadoria
   manual só para `high`/`blocked`; nenhum `low` por maturidade de pesquisa (F48-14). Motivo:
   64,5 % das vagas estão em empresas `low` só porque a pesquisa é menos madura, não por
   interesse, o que afunda OpenAI, Anthropic, Databricks e Stripe no ranking.
5. **Vaga em N cidades (Bluelight).** Decidido em 2026-09-29: mostrar uma linha por `(empresa,
   título normalizado, fonte)` com "+N locais" e lista no detalhe; nada é fundido nem fechado
   (F48-10). Motivo: 1.420 vagas da Bluelight (12,6 % do acervo) afogam a lista; agrupar é
   reversível e preserva a busca por local.
6. **Ativar as ~40 empresas com ATS identificado e sem fonte.** Decidido em 2026-09-29: sim,
   com probe e `TERMS_REVIEWED=1` como hoje, depois de F48-01 estar implantado (F48-18).
   Motivo: é o maior ganho de cobertura sem código novo de coletor, dentro dos termos já
   revisados por tipo de ATS.
7. **Meta de senioridade `UNKNOWN`.** Decidido em 2026-09-29: meta de ≤ 30 % nas vagas com
   descrição, medida só depois do gabarito ampliado a ≥ 200 vagas; a meta antiga de ~25 % do
   F17-06 fica como aspiração, sem prazo (F48-15). Motivo: 93 % das vagas têm descrição e 47 %
   dos `UNKNOWN` trazem "N anos", mas sem precisão medida não se grava.
8. **Braintrust.** Decidido em 2026-09-29: continua **excluída** da coleta. O motivo do F20-56
   é a falta de endpoint estruturado, não cláusula de termos; a etiqueta "proibida" é corrigida
   nos documentos e em `FORBIDDEN_PLATFORMS` (F48-19). Só reentra com endpoint estruturado e
   revisão de termos próprios. A lista proibida (Gupy, Wellfound, YC/Work at a Startup,
   Careerflow, Crossover, Braintrust, Landing.jobs) fica inalterada.
9. **Fuso de `publication_date` da Remotive.** Decidido em 2026-09-29: gravar `published_at =
   None` para data sem fuso (F48-03); a recência cai na data de referência do F48-16. Só usar
   UTC se a documentação oficial disser, com link no card. Motivo: não inventar fuso; a perda é
   pequena (a data de coleta serve de base) e reprocessar é possível.
10. **Host do Docker dormir.** Decidido em 2026-09-29: o host da stack real deve ficar sem
    suspensão enquanto o radar coletar (ação do usuário no Windows: plano de energia sem
    suspensão na tomada), e o alarme de buraco do F48-07 permanece. Motivo: 3 slots de coleta
    perdidos (03Z, 06Z, 09Z) são compatíveis com host parado; sem coleta não há vaga nova, e o
    `restart: unless-stopped` já cobre o Docker, mas não o suspend do host.

Itens que continuam medição, não decisão (com o passo que os mede): causa exata do buraco de
coleta (F48-07: histórico de passadas e alarme); dia certo do "Who is hiring?" do HN (F48-21:
execução de 2026-10-03); janela real de quota do Groq (rodadas F20-22 a partir de 2026-09-30
00:00Z, comparando o uso relatado com o guard em UTC).

---

## 10. Respostas às incertezas do doc 47 (§8) e correções

- **Efeito real de P0-1:** medido; 46 elegíveis fora, 38 nunca coletadas (V01).
- **Salto de `REVIEW_REQUIRED` 4 → 185:** mecanismo achado (V12). Os 185 do v6 são
  `EXTERNAL_ID_CANONICAL_IDENTITY_CHANGED` (176 Nubank); o v6 mudou a regra de `work_mode`,
  que entra na impressão digital. Nada foi perdido, mas a oportunidade ficou desatualizada.
- **38 `FAILED`:** 35 Remotive + 3 manuais; hoje 99 com 61 HN (V02).
- **Coletores Workable/Teamtailor/Factorial/JobPosting e senioridade estruturada:** não
  verificado (segue aberto para F48-15).
- **Causa do buraco de 12 h:** não está no banco; há 3 slots de coleta perdidos (03Z, 06Z, 09Z),
  compatível com host parado *(inferido)*; ver V16.
- **Números do doc 47 §5 e do README (686 oportunidades):** eram de antes da importação de
  2026-09-29 (11.267). Atualizados para o snapshot de ~20:04Z junto com esta versão da SPEC.
- **Braintrust como "proibida" (doc 47 §8):** decidida (§9, decisão 8): exclusão mantida, motivo
  técnico registrado.
- **P2-7 (Workday via Tavily "sob teto"):** a premissa está errada; a Tavily falha em 100 % das
  páginas Workday (V09). O card correto é F48-08 + F48-19.

## 11. Verificação

Cada card traz critério de aceite e teste próprios (§5), no padrão da Fase 20. Nenhuma
chamada real a Tavily, Groq, Remotive ou ATS roda no CI (fixtures/`httpx.MockTransport`).
Números deste documento vêm de `SELECT` e de leitura de código em `844aafd`; reexecutar as
consultas do §2 antes de citar o funil em outro contexto, porque o banco muda.
