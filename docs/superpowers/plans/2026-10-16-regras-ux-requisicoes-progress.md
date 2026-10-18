# Progresso — Regras, UX e volume de requisições

## Estado atual da continuação — 2026-10-18

- O caso hostil de `html_text` recebeu patch e teste de regressão após a revisão da lentidão com aberturas de tag sem terminador: `test_html_text` passou 36 testes, e regressões de matching/normalização passaram 28. Separadamente, a suíte de regiões, `test_content_rule_activation` e `test_domain` reportou `295 passed in 4.97s`; a execução red de regiões registrou 3 falhas e a green após correção registrou 4 aprovados. Esses resultados focados não substituem a suíte backend completa.
- Ruff raw terminou com `All checks passed!`; mypy raw terminou com `Success: no issues found in 149 source files`. Os logs raw são `2026-10-18-r56-final-post-regions-ruff.stdout.log` e `2026-10-18-r56-final-post-regions-mypy.stdout.log`. `final-ruff`/`final-mypy` anteriores são saídas compactadas pelo RTK, não logs raw.
- RED histórico do harness: 5 falhas, 3175 aprovados e 11 skipped por montagens parciais (workflow ausente e frontend antigo). Com a montagem do worktree completo somente leitura, os cinco testes do harness passaram em 3,12 s. A falha backend histórica de `html_text` (1 falha, 3176 aprovados, 10 skipped) é uma fotografia separada anterior ao patch.
- A suíte backend completa da árvore atual terminou com `3181 passed, 10 skipped, 32 warnings in 635.11s (0:10:35)`, no stdout `docs/56-regras-ux-trafego/artifacts/2026-10-18-r56-final-backend-current-tree.stdout.log`.
- Este gate é uma fotografia local pré-publicação; push e CI estão sendo acompanhados no PR. A integração remota está em andamento, sem declarar merge ou conclusão remota.
- A evidência UX anterior antecede o patch final de `html_text` e permanece histórica. O replay offline atualizado e o digest da árvore final estão em `docs/56-regras-ux-trafego/ux-captures/report.json`.
- O digest do runner agora exclui os prefixos gerados também do diff rastreado. Um teste em repositório temporário isolado confirmou que alterar uma captura rastreada mantém o digest (`e3b0c442...b855`) e alterar uma fonte rastreada o muda (`44113b9c...34f41`).
- O replay final do Edge offline registrou 16 capturas, zero falhas e zero requests bloqueadas; quatro inspeções móveis não encontraram alvos menores que 44×44 px e oito focos da Inbox em 1440 px tiveram outline sólido de 3 px. A proveniência está no `report.json`; stdout/transcript foi preservado em `docs/56-regras-ux-trafego/artifacts/2026-10-18-r56-final-ux.stdout.log`. Essa evidência é visual e sintética, sem certificar WCAG ou produção.
- O gate local backend terminou com `3181 passed, 10 skipped, 32 warnings in 635.11s (0:10:35)`, exit 0. É uma fotografia pré-publicação; push e CI são acompanhados externamente na PR e o estado remoto não é declarado concluído. Ruff raw e Mypy raw passaram, conforme `docs/56-regras-ux-trafego/artifacts/backend-validation.md`.

## Continuação — fotografia anterior, 2026-10-18

- O trabalho inicial está publicado como PR draft [#112](https://github.com/mathfrancisco/Opportunity-Radar/pull/112), no commit `abd3fbe05f7ed0e382407d51323cfdf3f10d4981`. Os commits locais `8e2695d` (SQL/resumo e intake backend) e `c147ac5` (intake frontend) ainda não foram enviados.
- A redução SQL agrupa contagens por `profile_version_id` e carrega fallback de perfil uma vez. No benchmark sintético de 1.000 vagas, `all_areas` registrou 1/2/2 statements para 0/1/20 buscas, contra 1/2/21 no caminho legado; fallback ficou em 4 statements para 1 e 20 buscas. Em 20 filtros variados, legado: 21 SQL e 0,713900 s; resumo: 2 SQL e 0,092617 s, com igualdade verificada. Isso demonstra redução de round trips nesse conjunto, não custo de CPU ou latência constante.
- A mudança local de Intake combina aquisição e normalização em um POST `/sources/{source_id}/manual-intake`. Pode executar múltiplas transações/escritas SQL; portanto, um POST HTTP não significa uma única escrita. Em falha de normalização, o erro estruturado inclui `run_id` para recuperação. O `threadpool` protege o event loop. Os resultados pré-merge foram 65 testes SQL aprovados, seis avisos em 13,95 s e Ruff limpo; frontend: 49 testes em dois arquivos e lint limpo. Estes resultados ainda não validam a árvore integrada.
- A integração local de `main` em `b5f137349e5729f870a094aed628c84f9554631e` está em andamento, sem conflitos não resolvidos reportados. Correções de revisão ainda aguardam teste. Não há commit dessa integração nem envio dos dois commits locais.
- A `main` já contém R55-D2 a D6. Preserve os pesos upstream; não atribua essa entrega a R56 nem descreva D2 como globalmente pendente. Continuam sem evidência os rótulos humanos de senioridade (300 entradas, 0 rotuladas) e conteúdo (0/200); não declarar precisão nem fase completa.
- A evidência do commit `abd3fbe` abaixo é histórica e antecede os patches SQL/Intake e a integração. Revalide após estabilizar a árvore. `TENANCY_OWNER_API_READY` permanece fechado; não houve acesso ao banco operacional, deploy ou merge remoto.

### Evidência da árvore integrada — fotografia anterior

- `npm run check` integrado terminou com saída 0: lint, typecheck, 50 arquivos/479 testes e build em 2,09 s. O build mantém aviso de chunk acima de 500 kB.
- Testes focados integrados: backend 304 aprovados, três avisos, 18,80 s; frontend 84 aprovados.
- Naquela fotografia, o gate completo de backend, tráfego e UX ainda aguardavam execução. Esses resultados locais não confirmaram CI ou push.

### Evidência integrada anterior à correção de `html_text` — 2026-10-18

- A matriz sintética registrou 35/35 testes: Overview 5/5/5 GET, resumo de buscas 1 GET para 0/5/20 buscas, Intake 1 POST e até um refetch por chave ativa afetada, remount/TTL fresco sem GET adicional e cinco minutos ocioso sem polling. Proveniência: HEAD `c147ac5bf5aa3a07d258165374ae8ceeb0b0ce05`, árvore suja; não é CI nem produção.
- A fixture de AI budget foi alinhada ao contrato `models[]` e ao erro quando falta orçamento; Overview focado ficou em 19/19 testes, lint e typecheck com saída 0.
- O replay UX daquela árvore gerou 16 capturas com Edge instalado e APIs offline: zero falhas e zero requests bloqueadas/inesperadas. A inspeção cobriu mobile/desktop e controles móveis; o cartão de orçamento aparece como “Desligada” na fixture. O replay antecede a correção de `html_text` e não valida visualmente a árvore atual.
- O gate backend daquela árvore terminou com 1 falha, 3.176 aprovados, 10 skipped e 32 avisos em 594,58 s. A falha foi o caso hostil de `html_text` (7,17 s contra limite de 0,5 s), também reproduzido em Python 3.12.8 em 6,652 s. O patch foi aplicado depois; a repetição completa segue **PENDENTE**. Mypy e Ruff passaram na fotografia atual, conforme as saídas acima.
- O gate completo de backend e CI permanecem abertos. As amostras humanas seguem insuficientes: senioridade 300/0 rotuladas e conteúdo 0/200.

## Identidade e estado registrado — fotografia de 2026-10-17

- Plano: `docs/superpowers/plans/2026-10-16-regras-ux-requisicoes.md`
- Base capturada: `origin/main` em `a7f62e302dc7633a005c5e7ada66402e0fa71435`.
- Checkout de implementação e validação frontend:
  `C:\\Users\\mathf\\Documents\\GitHub\\Opportunity-Radar\\.worktrees\\r56-rules-ux-traffic`.
- Runtime frontend: `C:\\Users\\mathf\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe`
  (`v24.19.0`).
- No estado registrado em 2026-10-17 não havia commit/push. Desde então, o trabalho inicial foi publicado em draft PR #112; os commits locais citados acima seguem sem push. Não houve deploy, migração operacional, reclassificação ou acesso ao banco operacional; migrations foram executadas somente no banco efêmero isolado do gate. `TENANCY_OWNER_API_READY` permanece fechado.
- O check completo do frontend encerrou com saída 0. A revisão independente final não encontrou
  issues na evidência consolidada: baseline com 17 cenários e resumo final com 33, hashes,
  manifestos, contagens por rota e p50/p95 foram verificados; os hooks seguem GET v1, escrita e
  GET v2. O gate backend terminou com saída 0 em banco efêmero isolado: 2728 passed, 10 skipped,
  15 warnings, em 390.97 s.

## Fases e evidência disponível

1. **T1 — baseline reproduzível:** a base Git e o protocolo de comparação foram preservados.
   Não há baseline operacional de banco ou produção declarada por este documento.
2. **T2 — regras R55 de país e senioridade:** D1 e D3 foram implementados nesta frente. D2 a D6 chegaram depois pela `main`; preserve as definições upstream, sem atribuí-las a R56. O gate histórico não valida a integração atual.
3. **T3 — estados desconhecidos e encerramentos:** implementação feita pela frente responsável;
   o gate backend isolado passou, sem abrir tenancy, executar migração operacional ou reclassificar dados.
4. **T4 — protótipo UX:** protótipo foi aprovado antes das alterações visuais. As capturas e a
   comparação visual estão registradas em `docs/56-regras-ux-trafego/ux-captures/`; elas não
   demonstram dados de produção, cache real ou backend.
5. **T5 — frescor, retry e cancelamento:** a fábrica de query centraliza stale times, retry GET
   limitado e ausência de polling. `src/lib/queryClient.test.ts` passou com 3 testes. A matriz
   final foi revisada sem issues, com baseline de 17 cenários e resumo de 33; as contagens,
   p50/p95 e a sequência GET v1/escrita/GET v2 têm manifestos e hashes próprios.
6. **T6 — resumo de buscas salvas:** contrato e UX foram implementados pelas frentes próprias.
   O gate backend de 2.728 testes é anterior ao patch SQL. O benchmark do patch, também pré-merge,
   registra 1/2/2 statements em `all_areas` para 0/1/20 buscas e fallback de 4 statements para
   1/20 buscas; ver [summary-api.md](../../56-regras-ux-trafego/summary-api.md).
7. **T7 — UX aprovada:** Inbox, detalhe, Pipeline, Overview, Status e revisões correlatas foram
   alterados nas frentes responsáveis. A Inbox tem 31 testes focados aprovados, incluindo URL,
   histórico do Router e limpeza de rascunho ao aplicar busca salva sem termo. Isso não substitui
   o gate amplo do frontend.
8. **T8 — métricas, CI e rollback:** o `npm run check` completo terminou com saída 0 após
   apontar `TEMP` e `TMP` para `apps/web/.tmp`: lint, typecheck, 48 arquivos/431 testes Vitest e
   build passaram. O snapshot dele foi substituído pelo replay estreito de tráfego corrente
   (`request-metrics-final.json`, SHA-256 `4AA64231...4EBE`, digest de fonte
   `a614db4f...b777`). O backend isolado também passou; isso não substitui evidência de CI.

## Verificações frontend concluídas

- Recuperação de dependências: o `npm ci --no-audit --no-fund` autorizado terminou com saída 0
  usando o runtime acima. A tentativa sandbox anterior falhou internamente no npm com
  `Exit handler never called`; nenhum `node_modules` foi removido manualmente.
- Pacotes confirmados após a recuperação: Vitest `5.0.1`, jsdom `30.0.1` e std-env `4.2.0`.
- `npm run test -- src/lib/queryClient.test.ts`: 3/3, saída 0.
- `npm run test -- src/routes/InboxPage.test.tsx`: 31/31, saída 0.
- `eslint src/routes/InboxPage.tsx src/routes/InboxPage.test.tsx --max-warnings=0`: saída 0.
- `npm run test -- src/app/RouteGuards.test.tsx`: 7/7, saída 0; a asserção agora exige o
  `AbortSignal` que a query de sessão fornece ao `privateFetch`.
- `npm run check` com Node 24.19.0, `TEMP`/`TMP` locais e métricas finais: saída 0; lint,
  typecheck, 48/48 arquivos e 431/431 testes, seguido de `vite build` em 4.88 s.
- A matriz histórica do commit `abd3fbe` registra 35 testes aprovados, com baseline de 18 testes e 17
  skips no recorte correspondente. A prova é vinculada ao artefato de tráfego corrente, não ao
  hash snapshot produzido pelo check amplo.
- O gate backend final registrou saída 0: `2728 passed, 10 skipped, 15 warnings` em `390.97 s`
  (0:06:30), contra banco efêmero isolado. A saída literal e a proveniência são mantidas em
  `docs/56-regras-ux-trafego/artifacts/backend-validation.md` e `summary-api.md`.
- Saídas literais, duração e proveniência estão em
  `docs/56-regras-ux-trafego/artifacts/frontend-gate-dependencies.md`.

## Limites do gate final

- O primeiro gate capturado terminou com saída 1 por `ENOENT` no diretório AppData temporário do
  sandbox antes da coleta de testes. A repetição foi justificada e executada com `TEMP`/`TMP`
  dentro da worktree, produzindo a saída 0 registrada no artefato frontend.
- O build mantém um aviso de chunk de 665.98 kB (191.09 kB gzip); não é falha e não foi alterado
  nesta frente.
- A matriz histórica registra dois POSTs de Intake (`submitManualRun` e `normalizeRun`). O patch
  local posterior os combina em um POST HTTP `manual-intake`, que ainda pode executar várias
  escritas SQL. O comportamento integrado não foi validado.
- Nenhuma linha desta nota substitui a validação isolada do backend, a comparação de métricas,
  ou as verificações de CI. Cada uma precisa de sua saída literal e proveniência.

## Rollback local seguro

- Antes de qualquer reversão seletiva, capturar `git diff` e a lista de arquivos não rastreados
  da worktree, preservando mudanças concorrentes e artefatos necessários.
- Reverter somente o arquivo ou hunk identificado, por patch reverso revisável; não usar
  `git reset`, `git restore` amplo, limpeza recursiva ou remoção de junctions em uma worktree
  já suja.
- Como há commits locais sem push e um PR draft publicado, o retorno deve preservar o snapshot
  atual e ser verificável por diff/patch seletivo. Não habilitar tenancy, executar migração ou
  reclassificar dados como atalho de rollback.

## Histórico de preparação — 2026-10-16

A preparação original registrou o SHA de base, isolou a worktree e reservou o harness de métricas
para a etapa final. A regra de não executar validações intermediárias foi superada pela autorização
posterior para a validação final coordenada. Os detalhes da preparação e os limites de cada
artefato permanecem nos documentos de decisão e evidências adjacentes.

## Gate local final pré-publicação — 2026-10-18

A suíte backend na árvore completa somente leitura terminou com `3181 passed, 10 skipped,
32 warnings in 635.11s (0:10:35)`, exit 0; Ruff raw e Mypy raw passaram conforme
`docs/56-regras-ux-trafego/artifacts/backend-validation.md`. O replay UX offline atual
gerou 16 capturas, zero falhas e zero requests bloqueadas; digest e checagens estão em
`docs/56-regras-ux-trafego/ux-captures/report.json`. Esta é uma fotografia local
pré-publicação. Push e CI são acompanhados externamente na PR; nenhuma conclusão de merge
remoto é afirmada. Persistem os limites de amostras de senioridade (300/0 rotuladas) e
conteúdo (0/200), sem alegação de precisão ou certificação de acessibilidade.
