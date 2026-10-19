# Plano de implementação — landing e autenticação

> **Para agentes:** SUBSKILL OBRIGATÓRIA: execute este plano tarefa a tarefa com `superpowers:executing-plans`. Os passos usam caixas (`- [ ]`) para acompanhamento.

**Objetivo:** Apresentar Opportunity Radar como um produto claro e profissional e integrar visualmente as rotas existentes de entrada e cadastro do Clerk.

**Arquitetura:** Manter a narrativa pública e a demonstração estática em `LandingPage`, com CTAs `<Link>` locais para o roteador existente controlar a navegação. Manter os fluxos `SignIn` e `SignUp` do Clerk, envolvendo-os em um shell de rota que fornece contexto da marca e retorno para a landing. Aplicar a localização oficial `ptBR` por `ClerkProvider` se o pacote oficial compatível for necessário.

**Stack:** React 19, React Router 7, Clerk React 6, Tailwind 4, Vitest.

**Especificação:** `DESIGN.md`; pedido de 2026-10-18 para landing profissional e tela de login, com direção visual delegada pelo usuário.

## Restrições globais

- Use the existing petroleum/slate tokens, local Inter font, visible 3px focus, and 44px mobile targets.
- No gradients, diffuse shadows, animation, new API calls, polling, prefetching, external images, or invented product claims.
- The preview is static HTML/CSS and visibly labelled as fictional demonstration data.
- Public copy describes personal-use features only; sources and homologation remain owner-only operations.
- Preserve Clerk path routing, recovery/OAuth screens, sign-in state redirects, owner protection, provider configuration, and Development mode notices.

## Foco da revisão

- A visitor can reach local `/sign-in` and `/sign-up` CTAs without a hosted redirect wrapper.
- A deep Clerk callback or recovery path retains the correct `path`, adjacent auth URL, and fallback redirect.
- Keyboard users can open and close FAQ disclosures and see the global focus ring.
- The responsive preview does not create horizontal overflow at a 360px viewport.
- A signed-in visitor still bypasses public/auth shells to the existing overview and protected routes remain protected.

### Tarefa 1: Narrativa pública e demonstração da landing

**Files:**
- Modify: `apps/web/src/routes/LandingPage.tsx`
- Modify: `apps/web/src/app/App.test.tsx`

- [x] Write focused assertions for headings, local CTA hrefs, the fictional-data label, and native FAQ disclosures.
- [x] Run `npm test -- src/app/App.test.tsx` and observe the missing public structure.
- [x] Implement the anchored landing sections, static inbox/match/pipeline preview, and responsive navigation with semantic HTML.
- [x] Re-run the focused test and inspect desktop/mobile rendering locally.

### Tarefa 2: Shell de autenticação Clerk e localização em português

**Files:**
- Modify: `apps/web/src/app/App.tsx`
- Modify: `apps/web/src/app/WebApplication.tsx`
- Modify: `apps/web/src/app/App.test.tsx`
- Modify: `apps/web/src/app/WebApplication.test.tsx`
- Modify only if absent: `apps/web/package.json`, `apps/web/package-lock.json`

- [x] Write focused assertions for the branded shell, home link, and preserved Clerk props.
- [x] Run the focused app tests and observe the missing shell/localization contract.
- [x] Wrap existing Clerk forms in the route shell; apply official `ptBR` localization only through the provider, adding `@clerk/localizations` only when absent.
- [x] Re-run focused tests, then `npm run check`; review anonymous shell and local deep paths without entering credentials.

## Auto-revisão

The two tasks cover the requested landing, local CTAs, preview, mobile/accessibility, Clerk shell, Portuguese component text, redirects, and existing protections. No API, database, credential, provider-instance, or owner-operation change is planned.

## Registro de execução — 2026-10-18

- A landing já presente no worktree foi preservada; os contratos de CTA local, preview fictício, FAQ nativo e rotas Clerk foram cobertos pelos testes. A navegação móvel passou a ocultar o texto do wordmark em telas pequenas, preservando o alvo de 44px.
- O `ClerkProvider` usa a localização oficial `ptBR` de `@clerk/localizations` 4.22.1. O shell de autenticação manteve as rotas com wildcard e recebeu alvo de toque de 44px no link da marca; os links do rodapé público também receberam esse alvo.
- Evidência focada: `src/app/App.test.tsx` e `src/app/WebApplication.test.tsx` passaram com 26 testes. O registro completo em `apps/web/.tmp/2026-10-18-landing-auth-check-interrupted.txt` mostra lint e typecheck concluídos, 50 arquivos/483 testes aprovados e build Vite concluído em 2.39s. A saída final não trouxe código de saída capturável pelo executor; o único aviso foi o aviso existente de chunk acima de 500 kB do Vite.
- A primeira tentativa visual local no Edge, com `VITE_CLERK_PUBLISHABLE_KEY=pk_test_placeholder`, alcançou a página de configuração de autenticação ausente. A fixture anônima posterior injetou o CSS compilado de produção e confirmou, em 360px, ausência de overflow, wordmark de 44×44px, CTAs de cabeçalho de 62×44px e 93×44px, links de rodapé entre 45×44px e 69×44px, e links da marca/retorno do shell com 44px de altura. A fixture representa apenas o shell e um placeholder de formulário Clerk; não verifica uma sessão ou formulário Clerk reais. Não foram inseridas credenciais nem usadas configurações de provedor reais. As capturas, fixture e logs temporários ficaram em `apps/web/.tmp`.
