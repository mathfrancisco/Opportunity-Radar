# Progresso — Regras, UX e volume de requisições

## Identidade e estado atual — 2026-10-17

- Plano: `docs/superpowers/plans/2026-10-16-regras-ux-requisicoes.md`
- Base capturada: `origin/main` em `a7f62e302dc7633a005c5e7ada66402e0fa71435`.
- Checkout de implementação e validação frontend:
  `C:\\Users\\mathf\\Documents\\GitHub\\Opportunity-Radar\\.worktrees\\r56-rules-ux-traffic`.
- Runtime frontend: `C:\\Users\\mathf\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\bin\\node.exe`
  (`v24.19.0`).
- Nenhum commit, push, deploy, migração, reclassificação ou acesso ao banco operacional foi
  criado nesta frente. `TENANCY_OWNER_API_READY` permanece fechado.
- O check completo do frontend encerrou com saída 0. A revisão independente final não encontrou
  issues na evidência consolidada: baseline com 17 cenários e resumo final com 33, hashes,
  manifestos, contagens por rota e p50/p95 foram verificados; os hooks seguem GET v1, escrita e
  GET v2. O gate backend terminou com saída 0 em banco efêmero isolado: 2728 passed, 10 skipped,
  15 warnings, em 390.97 s.

## Fases e evidência disponível

1. **T1 — baseline reproduzível:** a base Git e o protocolo de comparação foram preservados.
   Não há baseline operacional de banco ou produção declarada por este documento.
2. **T2 — regras R55 de país e senioridade:** D1 e D3 foram implementados; D2 (pesos) continua
   sem decisão e sem mudança. O gate backend em banco efêmero isolado passou com 2728 testes,
   mas não transforma a ausência de decisão de pesos em aceite de D2.
3. **T3 — estados desconhecidos e encerramentos:** implementação feita pela frente responsável;
   o gate backend isolado passou, sem abrir tenancy, migração ou reclassificação.
4. **T4 — protótipo UX:** protótipo foi aprovado antes das alterações visuais. As capturas e a
   comparação visual estão registradas em `docs/56-regras-ux-trafego/ux-captures/`; elas não
   demonstram dados de produção, cache real ou backend.
5. **T5 — frescor, retry e cancelamento:** a fábrica de query centraliza stale times, retry GET
   limitado e ausência de polling. `src/lib/queryClient.test.ts` passou com 3 testes. A matriz
   final foi revisada sem issues, com baseline de 17 cenários e resumo de 33; as contagens,
   p50/p95 e a sequência GET v1/escrita/GET v2 têm manifestos e hashes próprios.
6. **T6 — resumo de buscas salvas:** contrato e UX foram implementados pelas frentes próprias.
   O gate backend isolado final passou com 2728 testes; a prova SQL registra 1, 2 e 21 consultas
   nas áreas exercitadas e fallback de 4, sem depender de constante fixa.
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
- A matriz de tráfego corrente registra 35 testes aprovados, com baseline de 18 testes e 17
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
- O Intake ainda executa literalmente duas escritas (`submitManualRun` e `normalizeRun`) em sua
  interação. Logo, o orçamento de uma escrita por mutação não está atendido para esse fluxo e
  nenhuma nota declara todos os critérios aceitos.
- Nenhuma linha desta nota substitui a validação isolada do backend, a comparação de métricas,
  ou as verificações de CI. Cada uma precisa de sua saída literal e proveniência.

## Rollback local seguro

- Antes de qualquer reversão seletiva, capturar `git diff` e a lista de arquivos não rastreados
  da worktree, preservando mudanças concorrentes e artefatos necessários.
- Reverter somente o arquivo ou hunk identificado, por patch reverso revisável; não usar
  `git reset`, `git restore` amplo, limpeza recursiva ou remoção de junctions em uma worktree
  já suja.
- Como não houve commit, o retorno deve conservar esse snapshot e ser verificável por diff. Não
  habilitar tenancy, executar migração ou reclassificar dados como atalho de rollback.

## Histórico de preparação — 2026-10-16

A preparação original registrou o SHA de base, isolou a worktree e reservou o harness de métricas
para a etapa final. A regra de não executar validações intermediárias foi superada pela autorização
posterior para a validação final coordenada. Os detalhes da preparação e os limites de cada
artefato permanecem nos documentos de decisão e evidências adjacentes.
