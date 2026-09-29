# F48-08 — Workday sem Tavily e orçamento por tenant (V09, V10)

## Resultado

- Configuração `extraction_skip_source_types` (padrão `workday`) pula a extração da Tavily
  para tipos de origem especificados. Para qualquer host, depois de N falhas seguidas,
  nenhuma extração é tentada e a falha é registrada em `tavily_extract_cache` com cooldown
  (`TAVILY_EXTRACT_HOST_FAILURE_THRESHOLD`, padrão 5).
- Chamadas Tavily `/extract` são contadas em contador separado (`tavily_telemetry`), nunca no
  orçamento de host do ATS (`run_telemetry.http_requests`). O contador de requisições HTTP do
  ATS continua refletindo só as chamadas da coleta na fonte.
- Chave do orçamento persistido (`host_budget_state`) é por tenant para tipos com múltiplas
  locações (Workday, Teamtailor, Factorial, JobPosting): `workday:<tenant>:<region>`,
  `teamtailor:<company>`, `factorial:<company>`, `jobposting:<host>`. Tipos de host
  compartilhado (ex.: `hacker_news`) usam a chave física. Migração `20260929_0056`:
  para cada linha agregada existente, cria uma linha por tenant configurado com janela
  fresca e zero gasto, mantendo cooldown; depois apaga a agregada.
- Teto de requisições por tipo (`HOST_REQUEST_CEILINGS`, padrão `workday=500, hacker_news=500`)
  é usado só na criação de linha nova; linhas existentes preservam o teto que têm. Uma linha
  Workday criada nova tem teto ≥ 500 (uma grande board com ~20 itens por requisição cabe
  num bucket).

## Decisão: contador Tavily fora do orçamento do ATS

A Tavily é um provedor diferente do ATS (coleta vs. extração de conteúdo). Somá-la no
`http_requests` do host do ATS mascarava o orçamento: AIG Workday 518 requisições
(492 chamadas Tavily + 26 páginas); Adobe 244 (232 chamadas + 12 páginas). Com a mudança,
o orçamento do ATS diz o real: AIG de 18 runs vezes 26 requisições por run, ou menos.
Tavily tem orçamento próprio (`TAVILY_CREDIT_BUDGET_PER_RUN`, não mudado).

## Limites

- A parada por falhas sucessivas é por host (`workday:adobe:us`), não por tipo agregado.
  Uma falha em Adobe não afeta AIG.
- Workday por detalhe público (endpoint com descrição) segue para outro card (F48-19).

## Verificação

Suite completa **1.228 testes passaram, 11 skipped**. Migração `20260929_0056` testada
em ambas as direções (upgrade com tenants Workday, downgrade de volta). Testes em
`tests/backend/acquisition/test_host_budget_scheduling.py` (15 tenants em buckets separados,
coleta de 500 itens sem chamada Tavily), `test_service.py` (contadores Tavily à parte),
`test_tavily_extract_cache.py` (falhas sucessivas disparam cooldown),
`test_workday_collector.py` (descrição não é buscada com Tavily) e
`tests/backend/test_host_budget_migration.py` (roundtrip da migração).

Não testado contra stack real: se Adobe, após página 12, completa a paginação todo
(o teto 500 é o estimado; ver se de fato é suficiente numa run com placa real
vs. fixture). Telemetria de Tavily é contada em `CollectionTelemetry` mas não persiste
em banco; a observabilidade fica em logs por run.
