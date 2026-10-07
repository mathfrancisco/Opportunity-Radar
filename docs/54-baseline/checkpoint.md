# Checkpoint compacto — SPEC 54

Data: 2026-10-07. A orientação do produto prioriza F54 local antes de F53. Fase
atual: preparação e spike; migração visual depende do aceite previsto na SPEC §7.

## Checkout e preservação

Evidências deste diretório foram produzidas no checkout principal
`C:\Users\mathf\Documents\GitHub\Opportunity-Radar`, SHA
`b6d25ae96701398fa91e9214fe2a07985957cd19`. O SHA avançou de `e84be68` durante
esta execução; o diff de frontend/package/CSS entre eles é vazio. A worktree
`.worktrees/f54-primitives` contém o spike F54 não relacionado ao baseline de
produto; seus resultados 43/294 e seu ZIP ficam separados e não são citados como
evidência aqui. Outras worktrees F51/documentação e mudanças staged foram
preservadas. Este trabalho alterou somente `docs/54-baseline`.

Processos Node/Chrome compartilhados estavam ativos após as execuções. A leitura
de command lines via CIM retornou acesso negado; não encerramos processos para
evitar tocar processos alheios. O harness/observador fechou seus próprios
browsers e servidor loopback.

Check principal: exit 0, 42 arquivos e 292 testes; build concluído. Harness após
build: 55 capturas, SHA do commit/index/todos os assets registrado antes da
captura e verificado contra o dist antes dos polls; zero GETs sem fixture, zero
erros de página/console, zero respostas fixture não-200 e zero overflow. Polling
sequencial de 32 s: Inbox GETs em 0,206/15,219/30,235 s e Detalhe em
0,164/15,211/30,230 s. ZIP local read-only e SHA estão em
`artifacts/frontend-e84be68.zip` e `.sha256`; manifesto registra SHA real do
checkout e asset identity.

## WP0–WP7 e AC54

| Item | Estado verificado |
| --- | --- |
| WP0 baseline/inventário | concluído localmente: 48 exports, AnalysisPanel, mapa de rotas, métricas e 55 capturas |
| WP1 spike | em andamento em worktree separada; não validado por este baseline |
| WP2 protótipos | aguarda aceite visual explícito para Inbox, Detalhe e Pipeline |
| WP3 design system/wrappers | não iniciado; condicionado ao WP2 |
| WP4 rotas prioritárias | não iniciado; condicionado ao WP2/WP3 |
| WP5 rotas restantes | não iniciado |
| WP6 auth/regressão Clerk | pendente de F53 e fluxos reais autorizados |
| WP7 preview/release | pendente; ZIP é rollback local, sem cloud/deploy |

F53 não foi implementada e permanece adiada. AC54-01/08 aguardam F53;
AC54-02 aguarda aceite visual; AC54-10 cloud aguarda preview, smoke e rollback
cloud demonstrado. Nenhum AC54 é declarado completo.
