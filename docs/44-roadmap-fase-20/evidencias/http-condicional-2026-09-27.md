# HTTP condicional real — 2026-09-27

Evidência de execução real (não fabricada) para o item pendente de F20-38/F20-39: os
coletores de produção agora leem `request.conditional_headers`, enviam
`If-None-Match`/`If-Modified-Since` quando disponíveis, e reportam 304/`ETag`/
`Last-Modified` via `CollectionTelemetry`. Toda chamada de rede rodou contra boards
públicos reais, em volume pequeno, respeitando `robots.txt` e o ritmo de requisição, numa
pilha Docker Compose isolada (`-p f20cond`, `compose.yaml` + `compose.dev.yaml`). A pilha
real `opportunity-radar` não foi tocada, iniciada, parada nem sofreu `down -v`.

## Resumo

| Item | Resultado |
| --- | --- |
| Cabeçalhos condicionais enviados pelos 8 coletores | Feito — `acquisition/http_conditional.py` (helper compartilhado) + 8 coletores alterados |
| 304 real observado | Sim — Greenhouse (Lokalise) e Teamtailor (Seedtag) |
| Bytes evitados por um 304 | Medido diretamente por `curl`: 19.820 bytes (Greenhouse) e 345.111 bytes (Teamtailor) |
| Cursor real de retomada (Workday) | Feito e confirmado — offset 10 → 15, 5 itens novos, sem repetição |
| Retomada explícita (`resume_of_run_id`) sob uma queda real de processo | **Não exercida** nesta sessão — ver "O que fica pendente" |
| Migração `20260926_0042` (variantes de parser) | **Aceita** — teste de integração contra Postgres real |
| Orçamento por host compartilhado entre fontes reais | **Não exercido** — nenhum par de fontes reais usa o mesmo host |

## 0. Mudança de código

- Novo módulo `src/opportunity_radar/acquisition/http_conditional.py`: duas funções
  (`conditional_request_headers`, `record_conditional_response`) e a exceção
  `NotModifiedResponse`, usadas pelos 8 coletores em vez de duplicar a mesma lógica.
- Alterados: `ashby.py`, `greenhouse.py`, `lever.py`, `remotive.py`, `teamtailor.py`,
  `workable.py`, `factorial.py`, `workday.py`. Cada um agora: (1) envia
  `conditional_request_headers(request)` na chamada HTTP; (2) chama
  `record_conditional_response` em toda resposta que o servidor de fato devolveu; (3)
  levanta `NotModifiedResponse` num 304 bruto, capturada pelo próprio `discover()`, que
  então não emite itens nem chama `record_items_announced` (um 304 nunca prova um total,
  SPEC 39 §7).
- Lever e Workday (paginados) só enviam os cabeçalhos condicionais na primeira página
  (offset/skip 0): os validadores descrevem a leitura completa a partir do início, nunca
  uma página no meio, e uma retomada explícita por cursor não reenvia os cabeçalhos pela
  mesma razão.
- `workday.py` ganhou `_parse_cursor`, lê `request.cursor` como offset inicial e passa a
  preencher `CollectedItem.cursor` por item (`str(offset + index + 1)`, o ponto de
  retomada se a execução for interrompida logo depois daquele item).
- `CollectorCapabilities.etag`/`last_modified` passaram a `True` nos 8 coletores; Workday
  também ganhou `incremental_cursor=True`.

Testes novos por coletor (123 testes verdes ao todo nos 8 arquivos
`tests/backend/acquisition/test_{ashby,greenhouse,lever,remotive,teamtailor,workable,
factorial,workday}_collector.py`): envio de cabeçalho condicional quando o checkpoint tem
validadores, e um 304 bruto não emite itens nem anuncia um total. Workday ganhou também:
cada item carrega `cursor`; uma retomada com `cursor` explícito não reenvia cabeçalhos
condicionais (escopo diferente); um cursor malformado é recusado.

## 1. Preparação da pilha isolada

```
docker compose -p f20cond -f compose.yaml -f compose.dev.yaml up -d postgres
docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm --build migrate
docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm \
  -v "$(pwd):/workspace" api python scripts/import_research_catalog.py \
  --input /workspace/docs/pesquisas/auditoria-186-empresas.md \
  --input /workspace/docs/pesquisas/empresas-adicionais.md
```

Resultado do import real: 222 linhas processadas, 220 empresas criadas, 2 reconciliadas,
277 fontes candidatas, 52 em backlog — os mesmos números da homologação de 2026-09-26
(mesmos arquivos-fonte, catálogo real já existente no repositório).

Três `SourceDefinition` reais foram registradas na pilha `f20cond`
(`evidence_status: confirmed`, `terms_reviewed: true`, `collector_local_tested: true`):

| Fonte real | Tipo | `source_id` |
| --- | --- | --- |
| Adobe (`adobe/external_experienced`, `wd5`) | workday | `f3b13825-74c4-4d3f-bc92-552d6e42af51` |
| Seedtag (`jobs.seedtag.com`) | teamtailor | `1bda3b8c-9c23-4713-aa98-4a7716e5fb18` |
| Lokalise (`lokalise`) | greenhouse | `3247889f-c989-44d5-8cb4-ac5fe25e7369` |

Lokalise foi escolhida por já ter ATS Greenhouse confirmado na descoberta real de F20-27
(`docs/44-roadmap-fase-20/evidencias/homologacao-real-2026-09-26.md` §1). Adobe e Seedtag
repetem os dois boards já homologados em 2026-09-26, desta vez para medir o condicional.

## 2. Duas coletas reais, mesma pilha, `scripts/collect.py --max-items 10`

### 2.1 Primeira coleta (sem checkpoint ainda — cabeçalhos condicionais vazios)

| Fonte | `run_id` | status | items_seen | items_persisted |
| --- | --- | --- | --- | --- |
| Adobe (workday) | `6732abf2-2655-46c3-8639-b2ebd737727f` | SUCCEEDED | 10 | 10 |
| Lokalise (greenhouse) | `1ef29e4f-b49b-4ec5-92f6-b535cd189ce9` | SUCCEEDED | 2 | 2 |
| Seedtag (teamtailor) | `e74971d3-719b-4f43-b5a4-022193557483` | SUCCEEDED | 10 | 10 |

Checkpoint persistido depois da 1ª coleta (`acquisition.source_checkpoint`, consulta real
via `psql`):

```
source_definition_id                 | checkpoint_type | cursor | etag
f3b13825-... (Adobe/workday)         | cursor          | 10     | (vazio)
3247889f-... (Lokalise/greenhouse)   | cursor          |        | W/"eed1edefd3e2739e065d99813129c700"
1bda3b8c-... (Seedtag/teamtailor)    | cursor          |        | W/"cd168b4f1cfe257484cf2a6cc410e122"
```

Adobe/Workday não devolveu `ETag`/`Last-Modified` — confirmado real, não um bug do
coletor: o endpoint CXS (`POST /wday/cxs/.../jobs`) simplesmente não envia esses
cabeçalhos na resposta observada.

### 2.2 Segunda coleta, mesma configuração — 304 real

| Fonte | `run_id` | status | items_seen | items_persisted | observação |
| --- | --- | --- | --- | --- | --- |
| Adobe (workday) | `2c92976b-2302-421e-b51a-43be52cd5b0b` | SUCCEEDED | 10 | 0 (10 skipped) | sem 304 (sem validador para enviar); dedupe normal por hash de payload |
| Lokalise (greenhouse) | `b2f5e459-0adf-46a8-beaf-111cc82a82d7` | SUCCEEDED | **0** | 0 | **304 real** — nenhum item sequer chegou a ser avaliado |
| Seedtag (teamtailor) | `7465d9d9-9724-45e0-93a8-019036a046f4` | SUCCEEDED | **0** | 0 | **304 real** |

`run.complete` continuou `false` para as duas revalidações 304 (confirmado via `psql`):
nenhum manifesto foi declarado por esses coletores (`record_manifest`), então a 304 nunca
fecha o board como completo — exatamente a garantia que F20-39 exige (SPEC 39 §7).

### 2.3 Bytes evitados, medidos diretamente (fora do pipeline, para confirmar o header real)

```
curl -s -o /dev/null -w "greenhouse 200 body bytes: %{size_download}\n" \
  "https://boards-api.greenhouse.io/v1/boards/lokalise/jobs?content=true"
# greenhouse 200 body bytes: 19820

curl -s -o /dev/null -w "greenhouse 304 status: %{http_code} bytes: %{size_download}\n" \
  -H 'If-None-Match: W/"eed1edefd3e2739e065d99813129c700"' \
  "https://boards-api.greenhouse.io/v1/boards/lokalise/jobs?content=true"
# greenhouse 304 status: 304 bytes: 0

curl -s -o /dev/null -w "teamtailor 200 body bytes: %{size_download}\n" \
  "https://jobs.seedtag.com/jobs.json"
# teamtailor 200 body bytes: 345111

curl -s -o /dev/null -w "teamtailor 304 status: %{http_code} bytes: %{size_download}\n" \
  -H 'If-None-Match: W/"cd168b4f1cfe257484cf2a6cc410e122"' \
  "https://jobs.seedtag.com/jobs.json"
# teamtailor 304 status: 304 bytes: 0
```

Um revalidação 304 evitou 19.820 bytes no Greenhouse e 345.111 bytes no Teamtailor —
medido com o mesmo `ETag` real que o pipeline de produção persistiu no checkpoint.

## 3. Cursor real de retomada (Workday/Adobe)

`AcquisitionService.execute` foi chamado diretamente (script auxiliar, mesma pilha
`f20cond`) com `CollectionRequest(cursor=<checkpoint atual>, max_items=5)`:

```
checkpoint cursor before resume: '10'
resumed run status=SUCCEEDED items_seen=5 items_persisted=5 checkpoint_after=15
```

Consulta real (`acquisition.raw_item` join `acquisition.source_run`) confirma 15 vagas
reais e distintas da Adobe ao todo — as 10 da primeira coleta e as 5 novas da retomada,
sem nenhuma repetição de `external_id`:

```
/job/San-Jose/Forward-Deployed-Engineer_R171447-1                                      (run 1)
/job/San-Jose/Senior-Engineering-Program-Manager_R171555                               (run 1)
/job/San-Jose/Senior-Manager--Employee-Relations_R171834                               (run 1)
/job/San-Jose/Senior-Customer-Journeys-Technical-Consultant_R172032                    (run 1)
/job/Bangalore/Software-Development-Engineer_R171850                                   (run 1)
/job/San-Jose/Senior-Data-Architect_R172037                                            (run 1)
/job/Bangalore/Senior-Digital-Strategist_R169918                                       (run 1)
/job/San-Jose/AI-Solutions-Architect--Business-Process-Optimization_R171355            (run 1)
/job/London/Head-of-Government-Relations---Public-Policy--UKI-and-Middle-East_R171788  (run 1)
/job/Lehi/Legal-Counsel_R171633-1                                                      (run 1)
/job/Reading/Legal-Counsel_R171930                                                     (resumido, offset 10)
/job/San-Jose/Machine-Learning-Engineer_R171718                                        (resumido, offset 11)
/job/San-Jose/Machine-Learning-Engineer_R171719                                        (resumido, offset 12)
/job/New-York/Senior-Legal-Counsel--Privacy_R171569                                    (resumido, offset 13)
/job/Bangalore/Senior-Manager--Advanced-People-Analytics---Reporting_R169338           (resumido, offset 14)
```

Isso prova, com dado real, que Workday agora lê `request.cursor` como offset e que
`CollectedItem.cursor` avança item a item — o mecanismo que F20-39 precisa para que
`resume_of_run_id` tenha um cursor real para apontar.

### O que fica pendente sobre retomada

O teste acima usa um `cursor` explícito passado diretamente, não a cadeia completa
`resume_of_run_id` + uma queda real do processo: a primeira coleta terminou `SUCCEEDED`
(parada por `max_items`, não por uma falha), e `resumable_run` só nomeia execuções
`PARTIAL`/`FAILED` com evidência persistida. Fabricar uma queda de rede genuína contra o
board real da Adobe (por exemplo, cortar a conexão no meio de uma página) sem simular
dados ficou fora do tempo desta tarefa. O que foi provado é a leitura/escrita real do
cursor em si — a peça que faltava — não a orquestração completa de uma queda real de
processo, que segue coberta apenas por CI com coletores fake
(`test_crash_before_and_after_commit_resumes_idempotently`, já existente).

## 4. Migração `20260926_0042` (variantes de parser) — aceita

O card F20-39 registrava esse item como "implementação local sem aceite até validação no
banco compartilhado". `tests/backend/acquisition/test_parser_variants.py` já tinha testes
unitários (migração mockada); esta sessão adiciona
`test_a_real_parser_upgrade_appends_a_variant_instead_of_colliding`, que roda contra um
Postgres real (a mesma pilha `f20cond`, com `RUN_DATABASE_INTEGRATION=1`) e exercita o
caminho real de escrita de `AcquisitionService`:

1. Mesmo payload bruto, coletor emite `parser_version="example-v1"` na 1ª execução —
   persiste 1 `RawItem`.
2. Mesmo payload bruto, coletor emite `parser_version="example-v2"` na 2ª execução (uma
   mudança real de interpretação sobre os mesmos bytes) — persiste um **segundo**
   `RawItem` (mesmo `payload_hash`, `semantic_hash` diferente): a chave ampliada não
   colide, como o card pede.
3. Mesmo `parser_version="example-v2"` de novo na 3ª execução (revisita simples, sem
   mudança) — `items_persisted == 0`, presença confirmada, nenhuma terceira variante.

```
docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm \
  -e RUN_DATABASE_INTEGRATION=1 api pytest -q tests/backend/acquisition/test_parser_variants.py
# 5 passed
```

Critério de aceite cumprido; o card foi atualizado para "Aceito em 2026-09-27".

## 5. Validação

```
docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm \
  api pytest -q tests/backend/acquisition/test_{ashby,greenhouse,lever,remotive,teamtailor,workable,factorial,workday}_collector.py
# 123 passed

docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm \
  -e RUN_DATABASE_INTEGRATION=1 api pytest -q tests/backend/acquisition
# 275 passed, 8 skipped

docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm api ruff check .
# All checks passed!

docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm api mypy
# Success: no issues found in 116 source files

docker compose -p f20cond -f compose.yaml -f compose.dev.yaml run --rm \
  -e RUN_DATABASE_INTEGRATION=1 api pytest -q -p no:randomly
# 878 passed, 10 skipped
```

Uma primeira rodada da suíte completa (com a ordenação aleatória padrão) mostrou 2 falhas
intermitentes (`test_revisits_before_normalization_keep_per_run_observations`,
`test_catalog_owner_resolves_real_tavily_collector_item_without_company_name`) que passam
isoladamente e voltam a passar em uma segunda rodada completa com ordenação estável
(`-p no:randomly`); nenhum dos dois arquivos foi tocado por este trabalho — é
sensibilidade a ordem de execução pré-existente, não uma regressão introduzida aqui.

## 6. O que fica pendente e por quê

- Comparação real de 7 dias antes/depois (F20-38 critério 4): depende da janela de 7 dias
  do F20-35 (iniciada em 2026-09-26, termina 2026-10-04) mais operação contínua depois
  desta sessão — não pode ser fabricada nem apressada.
- Orçamento por host compartilhado entre duas fontes reais do mesmo host (F20-38): ainda
  não exercido — os 3 boards usados aqui são, cada um, o único host testado do seu tipo no
  catálogo importado.
- Retomada explícita (`resume_of_run_id`) sob uma queda real de processo contra um board
  real (F20-39 critério 3): não exercida nesta sessão — ver §3, "O que fica pendente sobre
  retomada". O mecanismo de cursor que ela depende foi provado real.
- Cursor de paginação para os outros 3 coletores novos (teamtailor/workable/factorial):
  continuam sem paginação real (o board inteiro é uma resposta só), então não há "meio de
  página" para eles ganharem cursor — fora de escopo desta tarefa (o card só pedia "ao
  menos Workday").
