# CARD F46-01 — DESIGN.md e tokens

- **Status:** Concluído em 2026-09-29 (pendência: cópia da imagem de referência, ver abaixo)
- **Fase:** 46 — Redesenho da interface web
- **Depende de:** Nenhum
- **Bloqueia:** F46-02 a F46-10
- **Origem:** [SPEC 46](../46-spec-redesign-ui.md), §4, §8, §9, §11, §13

## Resultado

`DESIGN.md` na raiz é a fonte de verdade de tokens e regras visuais; `styles.css` carrega os
valores neutros de §4.3 com os nomes de token de hoje; um teste falha se um par
texto/fundo documentado cair abaixo de 4.5 (texto) ou 3 (controle).

## Contexto

Não existia `DESIGN.md`. A paleta era verde-esverdeada com acento lima, sombra grande no
invólucro e Inter apenas declarada, sem ser carregada.

## Escopo

- Criar `DESIGN.md` (SPEC §4.1 a §4.3, D1 a D15).
- Trocar os **valores** dos tokens de `apps/web/src/styles.css`, mantendo nomes (D2), e
  adicionar `control-line`, `accent-surface`, `accent-ink`, `brand`, `radius-panel/control/
  chip`, `text-page-title`, `text-body-sm`, `text-caption`.
- Neutralizar o matiz dos tons semânticos mantendo contraste >= 4.5.
- Remover a sombra do invólucro (`PageShell`); `shadow-shell`, `rounded-shell`,
  `text-display*` e `mt-section` seguem definidos até F46-09.
- Logotipo mantém o lima original (D13) via novo token `brand`; o acento laranja é só de UI.
- Auto-hospedar Inter (R3).
- Teste Vitest `apps/web/src/styles.test.ts` sobre os valores de `styles.css`.
- Regenerar a tabela de contraste e apontar `docs/35-design-tokens.md` para o `DESIGN.md`.

## Fora de escopo

- Mudança estrutural de telas, sidebar, componentes novos (F46-02 em diante).
- Tema escuro.
- Cópia da imagem de referência: o arquivo não está no repositório e não foi inventado.
  **Pendente:** o usuário copia a captura para `docs/assets/`; `DESIGN.md` registra isso.

## Decisões de implementação

- **Inter (R3):** `@fontsource-variable/inter` instalou e empacota offline no build; subset
  latin via `@font-face` próprio em `styles.css`, `font-display: swap`, arquivo de ~48 KB
  emitido em `dist/assets`. Medição de LCP/CLS fica para F46-10.
- **`brand`:** sem ele o logotipo (`bg-accent`) viraria laranja ao trocar o valor de
  `accent`, contra D13. `PageShell` passa a usar `bg-brand` (única mudança de classe além
  da remoção da sombra).
- **`@types/node` + `types: ["node"]` em `tsconfig.app.json`:** o teste lê `styles.css` com
  `node:fs` (o `?raw` do Vitest devolve vazio para CSS). TypeScript 6 não inclui tipos
  ambientes por padrão.
- Consequência visível: o anel/sublinhado `accent` passa de lima a laranja onde já era usado
  (links, foco em fundo escuro); refinamentos de foco ficam nos cards de componente.
  `HomologationQueue` já usava `accent-surface`/`accent-ink`, antes sem definição; agora
  resolvem.

## Critérios de aceite

- [x] `DESIGN.md` existe na raiz com tokens, regras e decisões.
- [x] Valores de §4.3 aplicados; nomes preservados; tokens novos declarados.
- [x] Nenhum hexadecimal literal em `.ts/.tsx` (lint verde).
- [x] Cada par documentado >= 4.5 (texto) e >= 3 (controle), imposto por
      `styles.test.ts` (27 casos).
- [x] `docs/35-design-tokens.md` aponta para `DESIGN.md` e tem a tabela regenerada.
- [x] Invólucro sem sombra; logotipo com a cor original.
- [ ] Imagem de referência em `docs/assets/` (pendente do usuário).

## Verificação

`cd apps/web && npm run check` (lint, typecheck, test, build) verde em 2026-09-29; build
emite `inter-latin-wght-normal-*.woff2`. Contraste medido por script sobre `styles.css`
(ex.: `muted` sobre `canvas` 4.85, `accent-ink` sobre `canvas` 4.71, `control-line` sobre
`surface` 3.45).

## Arquivos

- `DESIGN.md`
- `apps/web/src/styles.css`, `apps/web/src/styles.test.ts`
- `apps/web/src/components/PageShell.tsx`
- `apps/web/package.json`, `package-lock.json`, `tsconfig.app.json`
- `docs/35-design-tokens.md`
