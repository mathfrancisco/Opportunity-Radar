# Homologação com dados reais — 2026-09-26

Evidência de execução real (não fabricada) para os cards F20-27 a F20-31, F20-35, F20-38 e
F20-39. Todo teste de rede rodou contra boards públicos reais, respeitando `robots.txt` e
ritmo de requisição, em pilha Docker Compose isolada (`-p f20real`, `compose.yaml` +
`compose.dev.yaml`). A pilha real `opportunity-radar` (dados do usuário) não foi tocada,
iniciada, parada nem sofreu `down -v` em nenhum momento.

## Resumo por card

| Card | Veredito | Evidência |
| --- | --- | --- |
| F20-27 | **Feito** — critério 4 cumprido | Execução real de `discover_ats.py`, ver §1 |
| F20-28 (Workday) | **Feito** — validado em 2 boards reais + achado e corrigido um gap de integração | §2.1 |
| F20-29 (Teamtailor) | **Feito** — validado em 2 boards reais, incluindo pipeline completo (`make collect`) duas vezes | §2.2 |
| F20-30 (Workable) | **Feito** — validado em 2 contas reais | §2.3 |
| F20-31 (Factorial) | **Feito** — validado em 2 boards reais; achado e corrigido um bug de parser | §2.4 |
| F20-35 | **Parcial** — janela de baseline de 7 dias iniciada, não pode terminar hoje | §3 |
| F20-38 | **Sem mudança** — critérios já cobertos por CI; item pendente (comparação real de 7 dias, ETag/Last-Modified nos coletores novos) confirmado como genuinamente pendente, não fabricável nesta sessão | §4 |
| F20-39 | **Parcial** — presença sem duplicação comprovada com dado real; retomada por cursor não é aplicável aos 4 coletores novos (nenhum define `item.cursor`) | §4 |

## 0. Preparação da pilha isolada

```
docker compose -p f20real -f compose.yaml -f compose.dev.yaml up -d postgres
docker compose -p f20real -f compose.yaml -f compose.dev.yaml run --rm --build migrate
docker compose -p f20real -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd):/workspace" api python scripts/import_research_catalog.py \
  --input /workspace/docs/pesquisas/auditoria-186-empresas.md \
  --input /workspace/docs/pesquisas/empresas-adicionais.md
```

Resultado do import real: 222 linhas processadas, 220 empresas criadas, 2 reconciliadas,
277 fontes candidatas registradas, 52 em backlog, 16 `SourceDefinition` de proposta
registrados. Nenhuma empresa do catálogo real foi inventada — os dados vêm de
`docs/pesquisas/auditoria-186-empresas.md` e `empresas-adicionais.md`, já existentes no
repositório.

## 1. F20-27 — Descoberta de ATS (critério 4)

Execução real de `make discover-ats` equivalente (`scripts/discover_ats.py`) contra as 115
empresas elegíveis (página de carreiras confirmada, sem ATS conhecido) do catálogo
importado, uma requisição por segundo, respeitando `robots.txt`:

```json
{
  "checked": 115,
  "by_ats": { "ashby": 3, "greenhouse": 1 },
  "no_ats_found": 111
}
```

Empresas com ATS revelado (via `company_radar.discovery_attempt`, sem nenhum dado de
candidato — só nome de empresa e URL pública de carreiras):

| Empresa | URL verificada | ATS |
| --- | --- | --- |
| LangChain | https://www.langchain.com/careers | ashby |
| Lokalise | https://lokalise.com/careers/ | greenhouse |
| Oyster | https://www.oysterhr.com/careers | ashby |
| Retell AI | https://www.retellai.com/careers | ashby |

Isso fecha o critério 4 do card F20-27 (relatório por tipo de ATS em `docs/pesquisas/`,
agora também nesta evidência): das 115 páginas de carreira sem ATS conhecido, 4 (3,5%)
revelam Ashby ou Greenhouse embutido; 111 continuam sem ATS estruturado detectável nesta
passada (não significa "sem vagas" — mesma nota do card).

## 2. F20-28 a F20-31 — coletores Workday/Teamtailor/Workable/Factorial

Cada coletor foi chamado diretamente (`discover()`, sem fabricação de dados) contra dois
boards públicos reais e bem conhecidos, escolhidos por mim (usuário não tinha
preferência), e também através do pipeline de produção completo para Teamtailor
(`scripts/collect.py` real, ver §2.2).

### 2.1 Workday (F20-28)

| Board | Tenant/site/pod | Resultado |
| --- | --- | --- |
| Adobe | `adobe/external_experienced`, `wd5` | 25 itens lidos (capado por `max_items`), título/local reais, `description=None` (o endpoint não expõe descrição — comportamento correto do card) |
| Workday (a própria empresa) | `workday/Workday`, `wd5` | 25 itens lidos (capado), mesma forma |

Amostra real (sem PII — só título de vaga e cidade):
- "Forward Deployed Engineer" — San Jose — `https://adobe.wd5.myworkdayjobs.com/external_experienced/job/San-Jose/Forward-Deployed-Engineer_R171447-1`
- "Software Development Engineer, SRE (US Federal)" — USA.VA.Reston

**Achado real (corrigido, ver commit `f51fa77`):** `AcquisitionService._collector_settings`
só sabia montar `CollectionRequest` para `ashby`/`lever`/`greenhouse`. Para
workday/teamtailor/workable/factorial retornava `(None, None, None)`, então uma fonte
homologada e habilitada desses 4 tipos falhava em **toda** execução real de coleta
(`INVALID_CONFIGURATION`, `company_reference` ausente) mesmo com o coletor correto — só a
sonda (`probing.py::run_probe`) já montava a requisição certo. Teste de regressão
(`test_workday_source_configuration_reaches_collector_via_execute`) comprova: sem o fix,
`run.status == "FAILED"`; com o fix, `run.status == "SUCCEEDED"` com item real persistido.

**Segundo achado real (corrigido, ver commit `676339c`):** mesmo com o fix acima,
`scripts/collect.py` (o `make collect` do operador) instanciava `AcquisitionService(session)`
sem registro, cujo padrão só conhece
`manual/ashby/lever/greenhouse/remotive` — nenhum dos 4 coletores novos, nem `tavily_search`.
Verificado ao vivo (§2.2): a mesma fonte real de Teamtailor que funcionava numa chamada
direta ao coletor falhava com `"collector is not registered: teamtailor"` ao passar pelo
`make collect` real, antes do fix.

### 2.2 Teamtailor (F20-29)

| Board | Domínio | Itens (chamada direta, sem cap) |
| --- | --- | --- |
| Seedtag | jobs.seedtag.com | 19 |
| Lingokids | jobs.lingokids.com | 2 |

Amostra real: "Sales Manager" — Milano — `https://jobs.seedtag.com/jobs/8432406-sales-manager`;
"Content LiveOps Manager" — Madrid — `https://jobs.lingokids.com/jobs/8433495-content-liveops-manager`.

**Validação pelo pipeline de produção completo (`make collect` real, após os dois fixes
acima):** registrada uma `SourceDefinition` real (`teamtailor`, `company_identifier:
jobs.seedtag.com`, `evidence_status: confirmed`, `terms_reviewed: true`,
`collector_local_tested: true`) na pilha `f20real`, e executado
`docker compose -p f20real ... run --rm api python scripts/collect.py --source-id <id>`
duas vezes seguidas:

| Execução | `run_id` | status | items_seen | items_persisted | items_skipped |
| --- | --- | --- | --- | --- | --- |
| 1ª (00:49:46 UTC) | `a39a9bfb-...` | SUCCEEDED | 19 | 19 | 0 |
| 2ª (00:50:02 UTC) | `f173c19d-...` | SUCCEEDED | 19 | 0 | 19 |

Isso é evidência real (não simulada em fixture) para o critério "duas visitas iguais
atualizam presença sem conteúdo duplicado" do F20-39: a segunda visita reconheceu as
mesmas 19 vagas, não persistiu nenhuma nova (`items_persisted: 0`) e contou as 19 como
"skipped" (dedupe por hash de payload), com timestamps reais de 16 segundos de intervalo.
Snapshot do `/search-metrics` (dashboard real) após as duas execuções, em
`docs/44-roadmap-fase-20/evidencias/f20-search-metrics-baseline-2026-09-26.json`:
`"runs": 2, "items_seen": 38, "items_persisted": 19, "items_duplicate": 19`.

### 2.3 Workable (F20-30)

| Conta | Slug | Itens |
| --- | --- | --- |
| Workable (a própria empresa) | `careers` | 1 |
| Wantable | `wantable-careers` | 4 |

Amostra real: "Office Manager" — `https://apply.workable.com/j/2ECE5A5123`; "Creative
Design Manager - Brand & Performance" — `https://apply.workable.com/j/F9263E6A0E`.
`location` veio `null` para essas vagas — confirmado no payload bruto da própria Workable
(campo `location` ausente no JSON), não é bug do coletor.

### 2.4 Factorial (F20-31)

| Board | Subdomínio | Itens |
| --- | --- | --- |
| Factorial (a própria empresa) | careers.factorialhr.com | 140 (board inteiro, sem paginação) |
| Agentero | agentero.factorialhr.com | 2 |

**Achado real (bug de parser, corrigido, ver commit `cbe206b`):** na primeira passada sem
cap, `careers.factorialhr.com` devolveu `count=131` mas `items_announced=140` —
`invalid_items=9`, todos com o mesmo erro: `"Factorial job is missing title, team or
location text"`. Investigação no HTML real mostrou a causa: uma vaga sem time atribuído
(`data-team-id=""`) ainda renderiza o `<div>` de rótulo do time, só que vazio; o parser só
adicionava o texto de um rótulo à lista de posições quando ele era não vazio, então o
rótulo vazio do time desaparecia e o texto do local (`location`) ficava, por engano, na
posição de time — sobrando só 2 textos em vez de 3, rejeitado como mudança de schema. Nas
9 vagas reais afetadas (ex.: "Partner Service Manager Spanish Market", "Engineering Team
Lead"), o problema nunca foi dado ausente ou HTML malformado — era uma vaga real, só sem
time, tratada incorretamente. Corrigido para sempre ocupar a posição do rótulo (mesmo
vazia); depois do fix, a mesma chamada real devolveu `count=140 == items_announced=140`,
`invalid_items=0`.

## 3. F20-35 — Mapa de cobertura e rendimento (janela de baseline)

Critério 4 do card exige baseline de 7 dias na máquina de referência antes de qualquer
mudança de agenda. Esta sessão **inicia** essa janela, sem poder terminá-la hoje:

- **Início da janela:** `2026-09-27T00:52:16.424759Z` (timestamp real do relógio do
  container `f20real-api-1`, gerado por `/search-metrics`).
- **Fim previsto da janela:** `2026-10-04` (7 dias depois).
- **Snapshot T0** salvo em
  `docs/44-roadmap-fase-20/evidencias/f20-search-metrics-baseline-2026-09-26.json`
  (chamada real ao endpoint `/search-metrics` da API rodando na pilha `f20real`, dados
  reais das execuções do §2.2 — não fabricado): `runs: 2`, `items_seen: 38`,
  `items_persisted: 19`, `companies_with_ats: 47`, `canonical_companies_total: 220`.
- **Pendente:** a pilha `f20real` não continua operando depois do fim desta sessão — o
  operador que assumir a janela precisa manter o worker de coleta (ou execuções
  periódicas de `make collect`) rodando por 7 dias reais e então repetir a chamada a
  `/search-metrics` para a comparação antes/depois. Fixtures não substituem essa medição
  (nota já presente no card); esta sessão não fabrica um "depois".

## 4. F20-38/F20-39 — agenda, HTTP condicional, delta e retomada

- **Presença sem duplicação (F20-39, critério 1):** comprovada com dado real, ver §2.2 —
  segunda execução real do mesmo source Teamtailor persistiu 0 itens novos e contou 19
  como vistos de novo.
- **HTTP condicional (ETag/If-Modified-Since) em produção (F20-38):** confirmado como
  genuinamente não aplicável ainda para os 4 coletores novos (Workday/Teamtailor/
  Workable/Factorial) — nenhum declara `CollectorCapabilities(etag=...)`/
  `last_modified=...`, nenhum lê `request.conditional_headers` nem chama
  `record_conditional_response`. Isso já era um item pendente documentado no próprio card
  F20-38 para os coletores mais antigos (ashby/greenhouse/lever/remotive); esta sessão
  confirma que os 4 coletores novos também não foram cabeados para isso — item real,
  fora do escopo desta validação (exigiria alterar a lógica HTTP de cada coletor, card
  futuro), não fabricado como concluído.
- **Retomada por cursor real (F20-39, critério 3):** não aplicável aos 4 coletores novos
  nesta forma real observada — nenhum deles (`workday.py`, `teamtailor.py`,
  `workable.py`, `factorial.py`) preenche `CollectedItem.cursor`, e três dos quatro
  (Teamtailor, Workable, Factorial) leem o board inteiro em uma única resposta HTTP sem
  paginação, então não há um "meio da página" real para retomar — a página seguinte,
  quando existe (Workday), sempre recomeça do offset 0 porque o coletor não lê
  `request.cursor`. A infraestrutura de retomada (`resume_of_run_id`,
  `AcquisitionRepository.resumable_run`) já existe e é testada em CI com coletores fake
  (comprovado no código, não reexecutado aqui); a retomada real com um desses 4
  coletores exigiria primeiro dar a eles um cursor de paginação, o que está fora do
  escopo desta tarefa de validação.
- **Orçamento por host compartilhado entre fontes (F20-38, critério 1):** não exercido
  com tráfego real nesta sessão — os boards reais usados aqui (Adobe/Workday em
  `*.myworkdayjobs.com`, Seedtag/Lingokids em `jobs.<empresa>.com`, Workable/Wantable em
  `apply.workable.com`, Factorial/Agentero em `*.factorialhr.com`) são, cada um, o único
  host testado do seu tipo — não havia duas fontes reais no catálogo importado
  compartilhando o mesmo host para observar o orçamento dividido em produção. A
  mecânica já é coberta por CI com fixtures determinísticas (`test_two_sources_same_host_
  share_budget_without_exceeding_ceiling`).

## 4.1 Homologação real completa via `make collect` (fecha o critério "empresa real
homologada e coletando" dos 4 cards)

Depois dos dois fixes do §2.1, registrada uma `SourceDefinition` real por ATS na pilha
`f20real` (`evidence_status: confirmed`, `terms_reviewed: true`,
`collector_local_tested: true`) e executado `scripts/collect.py` contra cada uma:

| Fonte real | Tipo | `run_id` | status | items_seen | items_persisted |
| --- | --- | --- | --- | --- | --- |
| Adobe (`adobe/external_experienced`, `wd5`, `--max-items 10`) | workday | `a1ea9b5b-...` | SUCCEEDED | 10 | 10 |
| Seedtag (`jobs.seedtag.com`) | teamtailor | `a39a9bfb-...` / `f173c19d-...` | SUCCEEDED (×2) | 19 / 19 | 19 / 0 |
| Wantable (`wantable-careers`) | workable | `38d3b5f3-...` | SUCCEEDED | 4 | 4 |
| Agentero (`agentero`) | factorial | `17b68596-...` | SUCCEEDED | 2 | 2 |

Todas as quatro fontes reais foram homologadas (campos de evidência marcados) e coletaram
com sucesso pelo pipeline de produção real (não uma chamada direta ao coletor) — fecha o
critério de aceite "pelo menos uma empresa real do catálogo homologada e coletando" para
F20-28, F20-29, F20-30 e F20-31.

## 5. Correções de código nesta sessão (commits)

1. `cbe206b` — `fix(acquisition): Factorial collector must not drop empty label divs`.
2. `f51fa77` — `fix(acquisition): wire Workday/Teamtailor/Workable/Factorial into execute()`.
3. `676339c` — `fix(acquisition): make collect use the full collector registry`.

Todos os três foram encontrados por execução real (não por leitura de código) e cada um
tem teste de regressão que falha sem o fix e passa com ele, mais `ruff check` e `mypy`
limpos nos arquivos tocados.

## 6. O que fica pendente e por quê

- F20-35 critério 4: precisa de 7 dias reais de operação após o início registrado aqui
  (§3) — não pode ser fabricado nem apressado.
- F20-38 comparação real de 7 dias antes/depois: mesma dependência de tempo real; além
  disso depende de ETag/Last-Modified estarem cabeados nos coletores em produção, o que
  ainda não está (nem para os coletores antigos, nem para os 4 novos).
- F20-39 retomada real por cursor com um coletor de produção: precisa que algum coletor
  real preencha `CollectedItem.cursor` — nenhum dos 4 novos faz isso hoje; não é um bug
  introduzido por esta tarefa, é um card futuro (o próprio F20-38 já lista isso como
  pendente para os coletores antigos).
- F20-32 (Gupy) permanece em Backlog, fora do escopo desta tarefa (só F20-28 a F20-31
  foram pedidos).
