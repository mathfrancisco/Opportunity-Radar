# Evidências de tráfego sintético

## O que este artefato mede

`apps/web/src/test/requestBudgets.test.tsx` usa componentes e hooks reais, uma identidade
de teste isolada e `fetch` offline. Ele registra tentativas HTTP que chegaram à camada de
transporte: método, rota sem query string ou identificador, status, resultado, categoria de
tráfego, ordinal cronológico, bytes conhecidos e duração sintética do fixture. O ordinal não
classifica retry: uma revisita, mutação ou nova operação continua sendo uma requisição distinta.
O campo `retry` fica `null` até que um cenário forneça correlação explícita da operação lógica;
o harness nunca deduz retry pelo ordinal.

O relatório não mede latência de produção, custo SQL, Clerk ou uma chamada de rede externa.
Sessão/autenticação e preflight `OPTIONS` recebem categorias próprias, separadas das contagens
de produto. `bytes`
é `null` quando a resposta sintética não pode ser lida; o protocolo nunca substitui esse valor
por zero.

## Replay final

Na etapa autorizada de validação, criar um checkout temporário separado no SHA congelado
`a7f62e302dc7633a005c5e7ada66402e0fa71435`. Não trocar o checkout desta entrega. Copiar
somente o suporte offline do harness quando ele ainda não existir no snapshot e executar a
matriz uma vez em cada estado:

1. baseline: política original (`retry: 1`, foco desabilitado, `staleTime: 0`), fixture
   `legacy` de saved searches;
2. final: `createQueryClient()` da árvore final, fixture `summary`;
3. fornecer `REQUEST_METRICS_BASELINE_SHA`, `REQUEST_METRICS_FINAL_REVISION` e
   `REQUEST_METRICS_FINAL_DIRTY` ao runner para registrar SHA do baseline e SHA/diff sujo
   da árvore final junto aos JSONs em `docs/56-regras-ux-trafego/artifacts/`.

Os cenários esperados são Overview inteira com 0/5/20 buscas salvas, Inbox fria e busca por
submit, detalhe, Pipeline ativa/encerrada, remount quente, cinco minutos ocioso, escrita com
invalidação, retry 5xx/rede, erros 401/403/409/422/429, cancelamento e mudança tardia de
identidade. Nenhum cenário deve inventar uma contagem quando a fixture não responder.

## Saída e CI

Definir `REQUEST_METRICS_MODE=final` e `REQUEST_METRICS_OUTPUT` faz o teste escrever JSON
sanitizado. O workflow do frontend publica `frontend-request-metrics` apenas como evidência
sintética. O arquivo não inclui token, query string, corpo, PII ou URL original de operação.

Os números de duração são relógio do fixture e não devem aparecer como desempenho do produto.
Os orçamentos finais só são avaliados depois de comparar ambos os relatórios da mesma matriz.

## Comandos reservados para o gate final

No replay do baseline, o checkout temporário recebe somente o suporte offline da matriz e um
`lib/queryClient.ts` de teste com os defaults originais (`retry: 1`, foco desabilitado e
`staleTime: 0`). Esse shim não importa a camada final de API nem os hooks finais: a árvore
baseline continua usando as implementações do SHA congelado. A árvore final usa a fábrica
real, cuja política classifica estritamente `HttpError` e `NetworkError`.

```powershell
# árvore final: dependências e gate completo que já inclui o harness
Set-Location apps/web
npm ci
$env:REQUEST_METRICS_MODE = 'final'
$env:REQUEST_METRICS_BASELINE_SHA = 'a7f62e302dc7633a005c5e7ada66402e0fa71435'
$env:REQUEST_METRICS_FINAL_REVISION = (git rev-parse HEAD)
$env:REQUEST_METRICS_FINAL_DIRTY = [bool](git status --porcelain)
$env:REQUEST_METRICS_OUTPUT = (Join-Path (Get-Location) 'request-metrics-final.json')
npm run check

# checkout separado, no SHA congelado: somente a matriz baseline copiada para esse checkout
$env:REQUEST_METRICS_MODE = 'baseline'
$env:REQUEST_METRICS_OUTPUT = (Join-Path (Get-Location) 'request-metrics-baseline.json')
npm run test -- src/test/requestBudgets.test.tsx
```

O comando baseline só é válido no checkout separado e não troca a árvore final. Se a instalação,
fixture ou componente impedir a execução, o relatório deve registrar a falha e não publicar zero
como medida.

## Replay histórico do commit `abd3fbe` — 2026-10-17

Os dois replays usaram Node `24.19.0`, fixtures offline que lançam em rota não registrada e
cache independente por cenário. O baseline foi um worktree temporário destacado em
`a7f62e302dc7633a005c5e7ada66402e0fa71435`; recebeu somente os dois arquivos do harness e
um shim de `queryClient` com `retry: 1`, `refetchOnWindowFocus: false` e `staleTime: 0`.
Não houve link/junction compartilhando `node_modules`.

`request-metrics-{baseline,final}.manifest.json` identifica cada matriz pelo SHA-256 de toda a
árvore `apps/web/src` e de `package-lock.json`, `vite.config.ts`, `tsconfig.app.json` e
`eslint.config.js`. O manifesto do baseline tem hash diferente porque contém o código congelado;
o final registra `savedSearchFixture: "summary"`. Os relatórios preservam a proveniência do SHA
congelado e marcam a árvore final como suja, portanto não representam um commit publicável.

| Cenário | Baseline | Final | Limite/resultado |
| --- | ---: | ---: | --- |
| Saved searches N=0/5/20 | 1/6/21 GET | 1/1/1 GET | resumo elimina N+1 |
| Overview N=0/5/20 | 4/9/24 GET | 4/4/4 GET | histórico; integração upstream acrescenta AI budget (alvo atual: <= 5) |
| Pipeline ativa | 2 GET | 1 GET | <= 1 |
| Pipeline encerrada | 2 GET no carregamento | 1 + 1 ao abrir | consulta adiada |
| Inbox fria / detalhe frio | 1 / 4 GET | 1 / 4 GET | <= 2 / <= 4 |
| Remount quente Inbox | 2 GET | 1 GET | sem refetch fresco |
| TTL vencido / reconexão fresca / obsoleta | n/a | 2 / 1 / 2 GET | um refetch somente quando obsoleta |
| Cinco minutos ocioso | 21 GET | 1 GET | zero polling adicional |

Todos os carregamentos de página da tabela tiveram `outcome: success`; uma fixture ausente falha o
teste. Os cenários de erro deliberado permanecem separados: 5xx faz duas tentativas com um retry
conhecido; 401/403/409/422/429, parser e escrita falha fazem uma tentativa; o cancelamento fica
como `cancelled`, sem bytes inventados. Cada relatório traz `routes` para cada cenário, agregado
por método, rota normalizada e categoria. Cada linha contém chamadas, erros, cancelamentos,
tentativas com classificação de retry conhecida e desconhecida, respostas com bytes conhecidos e
desconhecidos, e o total apenas dos bytes observados. `p50` e `p95` de `durationMs` usam
*nearest-rank* sobre todas as tentativas da rota; bytes `null` nunca entram como zero no total.
Esses tempos são somente do fixture.

As mutações históricas têm proveniência no código e testes focados em `requestBudgets.test.tsx`. Avaliação
refaz exatamente uma vez Inbox/Overview/saved-searches ativos; relevância grava uma vez e refaz
detalhe ativo uma vez. Perfil, aplicação e confirmação de duplicata têm cada uma um POST e um GET
inicial mais um refetch GET por chave invalidada, com cache da fixture passando de versão 1 para
2. Intake manual também prova, na matriz histórica, o transporte: há exatamente dois POSTs intencionais, um para criar
o run e outro para normalizá-lo, além de um GET inicial e um refetch por chave invalidada; não é
uma operação de um único POST. Cada teste exige duas execuções por chave ativa e cache versão 2,
impedindo refetch ativo duplicado.

Essas provas de mutação usam os hooks reais de escrita e invalidação. As queries ativas são
probes `useQueries` que fazem `privateFetch` para rotas de fixture e leem somente `{ version }`;
elas medem o transporte e a semântica de invalidação, mas não repetem o parse ou a apresentação de
todos os componentes consumidores. O resultado histórico de **2 POSTs por interação** não
representa o patch local posterior.

## Patch local de Intake — pré-merge, 2026-10-18

O patch introduz `POST /sources/{source_id}/manual-intake`, que combina aquisição e
normalização numa chamada HTTP; os endpoints legados permanecem compatíveis. A aquisição pode
persistir antes de uma falha de normalização. Nesse caso, a resposta estruturada
`manual_intake_normalization_failed` inclui o `run_id` capturado antes da normalização para
permitir recuperação. Rollback da sessão não desfaz necessariamente uma aquisição já persistida.
O caminho pode envolver múltiplas transações/escritas SQL, e o trabalho bloqueante usa
`threadpool` para não bloquear o event loop. Não há retry automático de POST.

O teste frontend pré-merge registrou 49 testes aprovados em dois arquivos e lint limpo. A
alteração reduz a interação a um POST HTTP, mas ainda não foi validada após integração com
`main`; a semântica de escrita única por mutação não pode ser inferida do número de chamadas HTTP.
O alvo continua a ser até um refetch por chave ativa afetada, aguardando evidência integrada.

## Observação de integração — fotografia anterior

O commit `abd3fbe` mediu Overview com quatro GETs. `main` acrescenta `useAIBudget`, que eleva o
objetivo integrado a cinco GETs, ainda dentro do limite. A tabela acima preserva a medição
histórica; ela não mede o código integrado. Regenere matriz e proveniência após estabilizar e
validar a integração. Não use os hashes históricos como hashes da árvore atual.

## Gate integrado parcial — fotografia anterior

`npm run check` terminou com saída 0: lint/typecheck, 50 arquivos/479 testes e
build em 2,09 s, com aviso de chunk acima de 500 kB. Os testes focados integrados
registraram backend 304 aprovados, três avisos em 18,80 s, e frontend 84
aprovados. Naquela fotografia, os checks ainda não tinham regenerado esta matriz nem a UX.

## Replay sintético integrado — evidência existente, 2026-10-18

O replay daquela fotografia registrou 35/35 testes aprovados. Overview fez 5/5/5 GETs para
0/5/20 buscas; `/saved-searches/summary` fez 1/1/1 GET; Intake fez um POST e no
máximo um refetch por chave ativa afetada. Remount quente e TTL fresco não
adicionaram GET, e cinco minutos ocioso não adicionaram polling. A proveniência
registra HEAD `c147ac5bf5aa3a07d258165374ae8ceeb0b0ce05` com árvore suja. Esta é
evidência offline sintética, não latência de produção, CI ou prova de banco.

O teste `OverviewPage.test.tsx` corrigiu a fixture do contrato `models[]` e a
asserção de erro quando o orçamento está ausente; Overview focado passou 19/19,
com lint e typecheck em saída 0.

O gate backend completo daquela fotografia terminou com 1 falha, 3.176 aprovados,
10 skipped e 32 avisos em 594,58 s. A falha era o caso hostil de `html_text`.
O patch foi aplicado depois; a repetição completa atual terminou aprovada conforme
o registro no plano de progresso. Mypy e Ruff raw também passaram.

A cobertura de UI para filtros malformados permanece no teste de Inbox por `invalid_filters`; ela
não é incluída como tráfego bem-sucedido.

## Verificação atual da proveniência — 2026-10-18

A reconstrução read-only do digest a partir de `sourceFiles` do JSON bate com
`357d328ef883d9cbbd8c9c1403441a45b0032a9701334b92e67460de154233c3`. O relatório
registra 33 cenários, com proveniência em
`reports[0].report.provenance`: HEAD `c147ac5bf5aa3a07d258165374ae8ceeb0b0ce05`,
árvore suja. As fontes de tráfego não mudaram desde a geração; a matriz existente
foi conferida sem repetir a suíte. Isso valida apenas o artefato e os cenários
reportados, não a árvore completa, backend ou produção.

O runner UX exclui os prefixos de saída gerada também do diff de arquivos rastreados.
O teste em repositório temporário confirmou digest estável após mudar uma captura
rastreada (`e3b0c442...b855`) e digest diferente após mudar uma fonte rastreada
(`44113b9c...34f41`). O replay final atual gerou 16 capturas, com zero falhas,
zero requests bloqueadas e digest em `ux-captures/report.json`; stdout/transcript em
`artifacts/2026-10-18-r56-final-ux.stdout.log`. O relatório valida apenas a fixture visual
offline, não backend ou produção.

Uma tentativa RED de suíte completa foi causada por montagens parciais do harness
(workflow ausente e frontend antigo): 5 falhas, 3175 aprovados e 11 skipped. Após
corrigir a montagem para o worktree completo somente leitura, cinco testes do harness
passaram em 3,12 s. Ruff raw terminou com `All checks passed!` e mypy raw com
`Success: no issues found in 149 source files`; logs raw: `2026-10-18-r56-final-post-regions-ruff.stdout.log` e `2026-10-18-r56-final-post-regions-mypy.stdout.log`. A suíte backend completa local terminou com `3181 passed, 10 skipped, 32 warnings in 635.11s (0:10:35)`, conforme `artifacts/2026-10-18-r56-final-backend-current-tree.stdout.log`. É uma fotografia pré-publicação; push e CI são acompanhados no PR, e a integração remota segue em andamento.
