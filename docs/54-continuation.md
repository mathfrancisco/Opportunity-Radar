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
| WP1 spike | Parcial, nenhum kit selecionado; seleção de biblioteca em andamento por autorização do dono em 2026-10-07 | Proveniência, acessibilidade e bundle dentro do orçamento |
| WP2 protótipos | 4 protótipos aceitos visualmente em 2026-10-07, com 2 ajustes aplicados e verificados pelo runner (ver `docs/54-review/README.md`, "Aceite visual") | Nenhuma para WP2; aceite não cobre F53, AC54-01/08/10 nem a SPEC como um todo |
| WP3 sistema/wrappers | Não iniciado; depende de WP2 | DESIGN.md e CSS juntos, tokens, foco, contraste, motion, wrappers e testes |
| WP4 rotas prioritárias | Não iniciado; depende de WP2/WP3 | Overview, Inbox, detalhe e Pipeline com contratos preservados |
| WP5 rotas restantes | Não iniciado; depende de WP2/WP3 | Companies, Company Detail, Sources, Homologation, Profile, Status e wildcard |
| WP6 auth/regressão | Pendente de F53 real | Clerk real e testes offline/estados de autorização |
| WP7 preview/release | Pendente de gates/autorização | Preview, smoke, comparação e rollback demonstrados |

### Critérios AC54

| Critério | Estado e evidência faltante |
| --- | --- |
| AC54-01 F53 operacional | Hosting, Clerk, backup/restore e aceite F53 ausentes |
| AC54-02 identidade aprovada | Aceite visual explícito dos 4 protótipos em 2026-10-07 (`docs/54-review/README.md`, "Aceite visual"); a identidade final ainda depende de WP3 (DESIGN.md/CSS) |
| AC54-03 biblioteca | Nenhum kit selecionado; spikes inconclusivas; seleção em andamento por autorização do dono em 2026-10-07 |
| AC54-04 componentes/tokens | Não iniciado; faltam wrappers, WCAG, testes e regressão |
| AC54-05 contratos/domínio | Não migrado; faltam testes de queries, filtros, scores, IA, forms e mutations |
| AC54-06 responsividade | Baseline não prova migração; faltam 10 rotas × 5 larguras e URL direta |
| AC54-07 WCAG 2.2 AA | Não provado: leitor de tela, zoom real, teclado, labels e contraste final |
| AC54-08 autenticação | Não iniciado; depende de Clerk/F53 real |
| AC54-09 performance | Sem bundle pós-migração; spike Radix aumentou JS gzip inicial 30,76 kB/20,64%, acima do limite +10% |
| AC54-10 release/rollback | ZIP local não prova preview, release ou rollback cloud |

## Revisão visual

`docs/54-review` contém Inbox, detalhe, Pipeline e Overview estáticos/sintéticos, em preview loopback `127.0.0.1:54154`, sem API, rede externa, persistência ou autenticação. Os quatro protótipos receberam aceite visual explícito em 2026-10-07; o aceite é somente da direção visual para WP3–WP5. O runner registrou 45 capturas (13 padrão e 32 estados), zero erros de JavaScript, sem overflow nos viewports reportados e verificações de Escape/foco do menu, ordem do painel de decisão e sete etapas da Pipeline em 1440 e 1280 px. O WP3B agora usa somente o Dialog aprovado para a gaveta móvel; isso não amplia o alcance da revisão visual.

As 45 evidências pertencem aos quatro protótipos e não equivalem à cobertura das 11 rotas finais (10 rotas e wildcard). As capturas da aplicação final para essas rotas em cinco larguras continuam pendentes. Os ajustes aceitos estão refletidos no protótipo: a Pipeline comporta as sete etapas em desktop sem rolagem horizontal e o painel “Sua decisão” aparece antes de “O que a vaga pede” em até 900 px, também nessa ordem no DOM. O relatório continua limitado aos protótipos e às asserções do runner; não comprova regressões na aplicação migrada. Zoom real do navegador, leitor de tela, reduced motion, dispositivos físicos e E2E continuam sem verificação. Overview exibe “2 novas desde última abertura”, métrica que deve ser mapeada ao contrato ou removida antes da migração.

## Spike de primitives

O WP3B aprovou exclusivamente `@radix-ui/react-dialog` 1.2.0, sob wrapper local,
para a gaveta de navegação móvel; a licença é MIT. No spike isolado, o único
Dialog mediu 149,01→161,62 kB de JS gzip (+12,61 kB / +8,54%), dentro do
orçamento de +10%. Essa comparação isolada não representa o bundle integrado.

Na medição integrada informada para o HEAD `a196780`, `npm run check` terminou
com exit 0 e Vitest reportou 42 arquivos / 336 testes. O JS inicial gzip mediu
163,65 kB e o CSS gzip, 7,33 kB. Contra o baseline aceito de 149,01 kB, o JS
aumentou 14,64 kB / 9,83%; o limite de +10% deixa 0,26 kB de margem. Contra o
último app integrado antes do WP3-B (150,07 kB), o aumento foi 13,58 kB / 9,05%.
A medição histórica de +20,64% corresponde ao primeiro spike mais amplo
(Dialog, Dropdown e Slot). Qualquer novo primitive exige medição comparável; se
o bundle ultrapassar +10%, o Dialog deve ser carregado sob demanda. A aprovação
não seleciona shadcn, outros primitives, rotas, estilos globais ou a SPEC 54.

## Validação e limites do ambiente

Node 24.12.0/npm 11.6.2. Relatos do ambiente dizem que runtime checks mostraram “not recognized” no sandbox e passaram elevados; não repita checks amplos sem motivo. Playwright está em `tests/e2e/browser/node_modules`; browser da CUA indisponível. Evite E2E com Compose operacional. Integração DB somente banco terminado em `_test` e `RUN_DATABASE_INTEGRATION=1`, `DATABASE_INTEGRATION_ISOLATED=1`; nunca usar banco operacional. `git diff --cached --check` da publicação encontrou whitespace literal preservado no log de check e em linha de contexto do patch; não alegar check limpo sem resolver com cuidado, sem alterar logs literais.

Retome pela seleção de biblioteca e pelo próximo menor pacote que satisfaça os gates. Registre evidência literal e incerteza; PR draft, baseline, captura ou protótipo não fecha F54.
## Branch e sequência prática

Este handoff foi publicado na branch `docs/f54-preparation-handoff-20261007`, criada sobre `3aaca63` (merge #70). Confirme o estado da branch e do PR ao retomar.

Ordem de trabalho: corrigir as pendências dos protótipos e do runner em escopo local; validar os protótipos localmente (concluído, com aceite visual em 2026-10-07); escolher biblioteca somente com orçamento e proveniência comprovados; então WP3 atualiza `DESIGN.md` e CSS juntos, seguido por WP4/WP5 nas dez rotas. WP6/WP7 continuam dependentes de F53 e autorização para preview/release. Preserve aplicação manual, filtros, scores, matching determinístico separado de IA e polling atual até decisão baseada em evidência.

Modelo de ownership: Sol/Astra coordenam e revisam read-only. Alteração de uma linha pode ser direta; trabalho maior deve ir para Luna/Terra (Luna como fallback), com arquivos/responsabilidade delimitados. No máximo três workers em tarefas independentes; workers não delegam. Faça revisão de diff separada e reporte os comandos/saídas realmente observados.
