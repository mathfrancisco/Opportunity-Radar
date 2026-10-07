# Prompt: continuar a SPEC 54 no Opportunity Radar

Copie este documento como prompt inicial da próxima sessão. Ele descreve o estado verificado para retomar a execução; não é aceite de F54.

## Objetivo e regras de execução

Continue a entrega local completa da SPEC 54 (WP0-WP7), respeitando os gates abaixo. O usuário priorizou F54 local e informou que nada da F53 foi implementado. Os protótipos receberam aceite visual explícito do dono do repositório em 2026-10-07 (ver `docs/54-review/README.md`, seção "Aceite visual"); o aceite é apenas visual. A autorização existente cobre a migração local sem nova confirmação para cada etapa prevista. Não deduza aceite de PR/capturas. Não crie cloud, Clerk real, deploy, serviços, migrações, alterações de API/banco ou dados reais sem gates e autorização específica.

Leia `AGENTS.md`, `C:\Users\mathf\.codex\RTK.md`, `DESIGN.md`, SPEC54, plano e roadmap F53, os READMEs e artefatos `docs/54-baseline`, `docs/54-review` e `docs/54-spike`. Use RTK em comandos suportados. Para mudanças criativas, escolha skills de engenharia/design adequadas; use `cavecrew-reviewer` para revisão read-only de diff. Consulte Context7 para documentação de versões atuais se a implementação depender disso. Identidade Git em Documents/GitHub: `mathfrancisco` / `math.francisco2@gmail.com`. Não reautentique nem faça logout de `gh`: sandbox falhou e auth existente funcionou elevado.

## Estado do checkout e preservação

A evidência baseline foi medida em `b6d25ae96701398fa91e9214fe2a07985957cd19`; verificação posterior encontrou `HEAD` e `origin/main` em `3aaca636341d70b5410d745e34a7785b6f6c28f5` (merge do PR #70). A diferença de frontend entre esses SHAs foi reportada vazia, mas o baseline continua sendo evidência apenas do SHA medido. Não altere metadados/hashes antigos sem repetir a execução correspondente. Verifique novamente branch, worktrees, divergência e alterações locais antes de trabalhar.

Preserve alterações e commits concorrentes. Não use operações destrutivas ou substituições de worktrees sem necessidade/autorização. Exclua `.tmp`, caches de teste, `.worktrees`, `node_modules`, segredos e dados privados de commits. O plano AWS Terraform é registro histórico de alternativa, não implementação. Nunca imprima credenciais/URLs privadas. Um worker Terra esgotou quota na sessão anterior; não prometa o resultado que faltou.

## Evidência e decisões pendentes

F53 não foi implementada: hosting, Clerk, backup/restore real, cutover/recuperação e Neon idle permanecem ausentes. O ZIP `frontend-e84be68.zip` é snapshot local read-only, com manifesto/hash do checkout `b6d25ae`; é rollback local, não prova de preview publicado ou restore real. F53 vem antes dos gates de Clerk/release da SPEC.

Baseline WP0 (preparação local, não AC54 completo): `npm run check` exit 0, 42 test files/292 testes, build Vite; 55 capturas sintéticas (10 rotas + wildcard em 320/360/768/1280/1440), fixtures para todas as chamadas API, bloqueio de rede externa, sem DB, zero erros/overflow nos viewports normais. Hashes de commit/index/assets foram preservados. Polls registrados: Inbox 0,206/15,219/30,235 s; detalhe 0,164/15,211/30,230 s. `apps/web/src/features/dashboard/useInbox.ts` e `apps/web/src/features/matching/useAssessment.ts` usam 15.000 ms; verificar refetchers sem manter Neon ativo.

Inventário: URLs `/`, `/inbox`, `/opportunities/:opportunityId`, `/applications`, `/companies`, `/companies/:companyId`, `/sources`, `/sources/homologation-queue`, `/profile`, `/status`, `*`; 48 exports nomeados, 29 arquivos de componentes, e AnalysisPanel adicional (fora dos 48). Preserve contratos, filtros, labels/ações, scores, deep links, aplicação manual e controles manuais de fontes. Matching determinístico é separado da IA; IA permanece consultiva e nunca aprova automaticamente candidatura/fonte/decisão humana.

### WP0-WP7

| Pacote | Estado verificado | Próxima evidência |
| --- | --- | --- |
| WP0 baseline/inventário | Preparação local validada; não AC54 | Rever contratos e polling na base aceita sem reescrever hashes históricos |
| WP1 spike | Concluído para o recorte aprovado: `@radix-ui/react-dialog@1.2.0` selecionado para a gaveta móvel; licença MIT | Reavaliar apenas se outro primitive entrar no escopo |
| WP2 protótipos | 4 protótipos aceitos visualmente em 2026-10-07, com 2 ajustes aplicados e verificados pelo runner (ver `docs/54-review/README.md`, "Aceite visual") | Nenhuma para WP2; aceite não cobre F53, AC54-01/08/10 nem a SPEC como um todo |
| WP3 sistema/wrappers | Implementado localmente | Manter validação proporcional para mudanças futuras; os limites de acessibilidade continuam abertos |
| WP4 rotas prioritárias | Migrado e revisado localmente | Evidência final local registrada em `docs/54-final`; preservar contratos de domínio em mudanças futuras |
| WP5 rotas restantes | Companies, Company Detail, Sources, Homologation, Profile, Status e wildcard migrados e revisados localmente | Evidência final local registrada em `docs/54-final`; não abre WP6/WP7 |
| WP6 auth/regressão | Bloqueado por F53, ainda não implementada | Clerk real e testes offline/estados de autorização após F53 |
| WP7 preview/release | Bloqueado por F53 e pelos gates/autorização | Preview, smoke, comparação e rollback demonstrados após F53 |

### Critérios AC54

| Critério | Estado e evidência faltante |
| --- | --- |
| AC54-01 F53 operacional | Hosting, Clerk, backup/restore e aceite F53 ausentes |
| AC54-02 identidade aprovada | Identidade implementada localmente em WP3; o aceite visual explícito dos 4 protótipos em 2026-10-07 (`docs/54-review/README.md`, "Aceite visual") permanece limitado aos protótipos. A aplicação final tem evidência local de 55 capturas em `docs/54-final`, sem que isso seja novo aceite de produto ou da SPEC |
| AC54-03 biblioteca | Seleção aprovada: somente `@radix-ui/react-dialog@1.2.0` sob wrapper local para a gaveta móvel; licença MIT |
| AC54-04 componentes/tokens | Parcial: WP3 implementado localmente e `npm run check` passou; a captura final não prova WCAG 2.2 AA, zoom real, leitor de tela, reduced motion ou todos os contrastes |
| AC54-05 contratos/domínio | Parcial: WP4/WP5 foram migrados com testes de rota focados; o harness final usa somente fixtures e não prova dados reais, mutações em produção, IA ou comportamento contra backend |
| AC54-06 responsividade | Evidência local concluída: 55 capturas da aplicação final (11 URLs diretas, incluindo wildcard, × 320/360/768/1280/1440) sem overflow, erros de página/console, APIs sem fixture ou fixture não-2xx; não substitui validação em dispositivos físicos |
| AC54-07 WCAG 2.2 AA | Não provado: leitor de tela, zoom real, teclado, labels e contraste final |
| AC54-08 autenticação | Não iniciado; depende de Clerk/F53 real |
| AC54-09 performance | Medição integrada final local: `npm run check` exit 0, Vitest 44 arquivos / 343 testes; JS inicial gzip 163,64 kB e CSS gzip 7,33 kB. Contra o baseline aceito de 149,01 kB, o JS continua dentro do limite histórico de +10%, mas qualquer mudança futura exige nova medição comparável |
| AC54-10 release/rollback | ZIP local não prova preview, release ou rollback cloud |

## Evidência visual final local

`docs/54-final/run-isolated-final.mjs` serviu o `apps/web/dist` já construído por loopback, sem Vite, Docker, API, backend ou rede externa. As respostas `/api` foram satisfeitas por `docs/54-baseline/fixtures.mjs`; o runner bloqueia qualquer outra origem e grava em `docs/54-final/result.json` a identidade do bundle, os requests e as asserções.

O resultado no commit `7e65a06b48301ddbb4a94a554609e4483e61e5ad` contém 55 screenshots em `docs/54-final/screenshots`: as 11 URLs diretas (`/`, `/inbox`, `/opportunities/opportunity-1`, `/applications`, `/companies`, `/companies/company-1`, `/sources`, `/sources/homologation-queue`, `/profile`, `/status` e `/missing` como wildcard) em 320, 360, 768, 1280 e 1440 px. Todas carregaram diretamente com status 200 e pathname solicitado, sem overflow horizontal, page errors, console errors, requests externos, APIs sem fixture ou respostas fixture não-2xx. A identidade gravada é `index.html` SHA-256 `3df7abe2a6d6e0035606cd49bb6478d38d8262d2905db8c7ad55adc9cdb3fe44`, mais hashes dos três assets servidos.

Esta é evidência local automatizada, não aceite visual adicional, WCAG global ou prova de produção. Zoom real, leitor de tela, reduced motion, dispositivos físicos e E2E Compose não foram exercitados. F53 permanece sem hosting, Clerk real, backup/restore e cutover; WP6 e WP7 continuam bloqueados por esses gates e por autorização específica.

## Spike de primitives

O WP3B aprovou exclusivamente `@radix-ui/react-dialog` 1.2.0, sob wrapper local,
para a gaveta de navegação móvel; a licença é MIT. No spike isolado, o único
Dialog mediu 149,01→161,62 kB de JS gzip (+12,61 kB / +8,54%), dentro do
orçamento de +10%. Essa comparação isolada não representa o bundle integrado.

Na medição integrada final após WP5, `npm run check` terminou com exit 0 e
Vitest reportou 44 arquivos / 343 testes. O JS inicial gzip mediu 163,64 kB e o
CSS gzip, 7,33 kB. Contra o baseline aceito de 149,01 kB, o JS permanece dentro
do limite histórico de +10%. A medição histórica de +20,64% corresponde ao
primeiro spike mais amplo (Dialog, Dropdown e Slot). Qualquer novo primitive
exige medição comparável; se o bundle ultrapassar +10%, o Dialog deve ser
carregado sob demanda. A aprovação não seleciona shadcn, outros primitives,
rotas, estilos globais ou a SPEC 54.

## Validação e limites do ambiente

Node 24.12.0/npm 11.6.2. Relatos do ambiente dizem que runtime checks mostraram “not recognized” no sandbox e passaram elevados; não repita checks amplos sem motivo. Playwright está em `tests/e2e/browser/node_modules`; browser da CUA indisponível. Evite E2E com Compose operacional. Integração DB somente banco terminado em `_test` e `RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1`; nunca usar banco operacional. `git diff --cached --check` da publicação encontrou whitespace literal preservado no log de check e em linha de contexto do patch; não alegar check limpo sem resolver com cuidado, sem alterar logs literais.

WP5 e a evidência final local estão concluídos. Registre evidência literal e incerteza em qualquer mudança futura; PR draft, baseline, captura ou protótipo não fecha F54.
## Branch e sequência prática

O estado de continuação verificado está na branch local `feat/f54-redesign-frontend`. Este pacote de evidências é local; nenhuma ação de PR ou publicação remota está autorizada.

Ordem de trabalho: não reabrir WP4/WP5 sem uma regressão concreta; manter evidência comparável após qualquer mudança relevante de bundle ou rota. WP6/WP7 continuam bloqueados por F53 e autorização específica. Preserve aplicação manual, filtros, scores, matching determinístico separado de IA e polling atual.

Modelo de ownership: Sol/Astra coordenam e revisam read-only. Alteração de uma linha pode ser direta; trabalho maior deve ir para Luna/Terra (Luna como fallback), com arquivos/responsabilidade delimitados. No máximo três workers em tarefas independentes; workers não delegam. Faça revisão de diff separada e reporte os comandos/saídas realmente observados.
