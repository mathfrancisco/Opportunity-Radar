# Prompt: continuar a SPEC 54 no Opportunity Radar

Copie este documento como prompt inicial da próxima sessão. Ele descreve o estado verificado para retomar a execução; não é aceite de F54.

## Objetivo e regras de execução

Continue a entrega local completa da SPEC 54 (WP0-WP7), respeitando os gates abaixo. O usuário priorizou F54 local e informou que nada da F53 foi implementado. Os protótipos ainda precisam de aceite visual explícito conforme SPEC §7 antes de WP3-WP5. Solicite uma revisão visual concreta; depois do aceite, a autorização existente cobre a migração local sem nova confirmação para cada etapa prevista. Não deduza aceite de PR/capturas. Não crie cloud, Clerk real, deploy, serviços, migrações, alterações de API/banco ou dados reais sem gates e autorização específica.

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
| WP1 spike | Parcial, nenhum kit selecionado | Proveniência, acessibilidade e bundle dentro do orçamento |
| WP2 protótipos | 4 protótipos aguardam aceite explícito | Revisão visual e decisão registrada |
| WP3 sistema/wrappers | Não iniciado; depende de WP2 | DESIGN.md e CSS juntos, tokens, foco, contraste, motion, wrappers e testes |
| WP4 rotas prioritárias | Não iniciado; depende de WP2/WP3 | Overview, Inbox, detalhe e Pipeline com contratos preservados |
| WP5 rotas restantes | Não iniciado; depende de WP2/WP3 | Companies, Company Detail, Sources, Homologation, Profile, Status e wildcard |
| WP6 auth/regressão | Pendente de F53 real | Clerk real e testes offline/estados de autorização |
| WP7 preview/release | Pendente de gates/autorização | Preview, smoke, comparação e rollback demonstrados |

### Critérios AC54

| Critério | Estado e evidência faltante |
| --- | --- |
| AC54-01 F53 operacional | Hosting, Clerk, backup/restore e aceite F53 ausentes |
| AC54-02 identidade aprovada | Falta aceite explícito dos 4 protótipos |
| AC54-03 biblioteca | Nenhum kit selecionado; spikes inconclusivas |
| AC54-04 componentes/tokens | Não iniciado; faltam wrappers, WCAG, testes e regressão |
| AC54-05 contratos/domínio | Não migrado; faltam testes de queries, filtros, scores, IA, forms e mutations |
| AC54-06 responsividade | Baseline não prova migração; faltam 10 rotas × 5 larguras e URL direta |
| AC54-07 WCAG 2.2 AA | Não provado: leitor de tela, zoom real, teclado, labels e contraste final |
| AC54-08 autenticação | Não iniciado; depende de Clerk/F53 real |
| AC54-09 performance | Sem bundle pós-migração; spike Radix aumentou JS gzip inicial 30,76 kB/20,64%, acima do limite +10% |
| AC54-10 release/rollback | ZIP local não prova preview, release ou rollback cloud |

## Revisão visual

`docs/54-review` contém Inbox, detalhe, Pipeline e Overview estáticos/sintéticos, preview loopback `127.0.0.1:54154`, sem API, rede externa, persistência ou auth. Relatório registra 44 capturas: 12 padrão (4 páginas em 1440/768/360) e 32 estados (4 em 1440/360), sem overflow nos viewports normais reportados. `verification.json`: zero erros JS; Escape fecha menu e devolve foco. Teste CSS zoom 200% em viewport 360 resultou 545/360 overflow; não é zoom real. Relatório não prova que o runner detecta regressões.

Pendências observadas: `.inbox-table thead` some em mobile e remove cabeçalhos para tecnologias assistivas; runner precisa assertions que falhem por regressão; timeout intermitente `[data-state]` sem causa diagnosticada; CSS/JS de alguns templates minificado. Overview exibe “2 novas desde última abertura”, métrica possivelmente sem dado; mapear ao contrato ou remover antes de migrar. Leitor de tela, zoom real, reduced-motion e dispositivos físicos não foram comprovados manualmente. Protótipos seguem sem aceite.

## Spike de primitives

Radix descartável baseado em `e84be68`: Dialog 1.2.0, Dropdown 2.1.25, Slot 1.4.0, MIT. Wrappers manuais inspirados em shadcn, sem proveniência de registry. Reporte local: 43 arquivos/294 testes, `npm check` e build passaram; JS gzip 149,01→179,77 kB (+20,64%, acima do orçamento de 10%). Não aprovar/selecionar sem resolver custo e proveniência. React Aria 1.21.1 e MUI 9.4.0 foram apenas pesquisados por metadados.

Segundo relato do worker, spike Base UI 1.8.0 teve testes unitários aprovados, mas Shift+Tab falhou no smoke real; check completo teria falhado por ESLint percorrer `node_modules.radix-archived`; limpeza parcial por binário bloqueado no Windows. Não há log literal completo desse relato. Fontes/manifests/teste/runner textuais estão em `docs/54-spike/artifacts/base-ui-source.patch`; diff usa paths relativos e `git apply --check` passou no momento da publicação. Arquivo é referência de revisão, sem dependências, binários ou worktree. Não publicar/reparar a worktree nem fazer terceira tentativa automática.

## Validação e limites do ambiente

Node 24.12.0/npm 11.6.2. Relatos do ambiente dizem que runtime checks mostraram “not recognized” no sandbox e passaram elevados; não repita checks amplos sem motivo. Playwright está em `tests/e2e/browser/node_modules`; browser da CUA indisponível. Evite E2E com Compose operacional. Integração DB somente banco terminado em `_test` e `RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1`; nunca usar banco operacional. `git diff --cached --check` da publicação encontrou whitespace literal preservado no log de check e em linha de contexto do patch; não alegar check limpo sem resolver com cuidado, sem alterar logs literais.

Retome pelo aceite visual e pelo próximo menor pacote que satisfaça os gates. Registre evidência literal e incerteza; PR draft, baseline, captura ou protótipo não fecha F54.
## Branch e sequência prática

Este handoff foi publicado na branch `docs/f54-preparation-handoff-20261007`, criada sobre `3aaca63` (merge #70). Confirme o estado da branch e do PR ao retomar.

Ordem de trabalho: corrigir as pendências dos protótipos e do runner em escopo local; validar os protótipos localmente; apresentar as telas para revisão concreta e obter aceite explícito; escolher biblioteca somente com orçamento e proveniência comprovados; então WP3 atualiza `DESIGN.md` e CSS juntos, seguido por WP4/WP5 nas dez rotas. WP6/WP7 continuam dependentes de F53 e autorização para preview/release. Preserve aplicação manual, filtros, scores, matching determinístico separado de IA e polling atual até decisão baseada em evidência.

Modelo de ownership: Sol/Astra coordenam e revisam read-only. Alteração de uma linha pode ser direta; trabalho maior deve ir para Luna/Terra (Luna como fallback), com arquivos/responsabilidade delimitados. No máximo três workers em tarefas independentes; workers não delegam. Faça revisão de diff separada e reporte os comandos/saídas realmente observados.