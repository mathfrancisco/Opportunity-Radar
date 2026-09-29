# F46-10 - Verificacao visual e E2E

Fonte: `docs/46-spec-redesign-ui.md` (8 F46-10, 9, 10, 11).

## Como foi rodado

Projeto Compose proprio (`e2e46`), nunca `opportunity-radar`:

```
docker compose -p e2e46 -f compose.yaml -f compose.ci.yaml up --detach --build api worker frontend
# importacao do catalogo (mesmo passo do CI) -> 220 empresas
cd tests/e2e/browser && npm ci && npx playwright install chromium
E2E_COMPOSE_PROJECT=e2e46 npx playwright test
cd apps/web && npm ci && npm run check
docker compose -p e2e46 -f compose.yaml -f compose.ci.yaml down -v   # so o proprio projeto
```

## Resultados

- Jornada existente (`01-happy-path`, `02-failure-scenarios`), antes de qualquer mudanca:
  `PASS (7) FAIL (0)`.
- Suite completa com o novo `03-visual.spec.ts`: `PASS (21) FAIL (0)`.
- `npm run check` (lint, typecheck, vitest, build): 39 arquivos, 273 testes verdes.

## Seletores alterados

Nenhum. A jornada passou sem mudar seletor (nenhum papel/rotulo mudou de proposito).

## Novo: `tests/e2e/browser/specs/03-visual.spec.ts`

- Por tela (Visao geral, Oportunidades, Candidaturas, Empresas, Fontes, Fila de
  homologacao, Perfil, Status, detalhe de vaga e de empresa): `scrollWidth <= innerWidth`
  em 320px e screenshot full-page em 1280 e 375.
- Teclado e foco: link "Pular para o conteudo" e o primeiro `Tab`, com anel e salto para
  `#conteudo`; links da sidebar em ordem, com anel; gaveta mobile abre pelo botao, `Esc`
  fecha e devolve o foco; pilulas de filtro com anel (o anel fica no wrapper por
  `focus-within`); paginacao com `aria-label`, anterior desabilitada, `aria-current` unico e
  proxima focavel com anel.
- Screenshots em `tests/e2e/browser/test-results/visual/<tela>-{1280,375}.png`. O CI ja
  envia `tests/e2e/browser/test-results/` no artefato `f20-47-browser-e2e-evidence`
  (`if: always()`), entao nao houve mudanca no `pipeline.yml`.

## Problemas reais corrigidos

1. Rolagem horizontal em 320px: Visao geral (515px), Fontes (460px) e Empresas (335px).
   - `DataTable`: o wrapper `overflow-x-auto` nao era `relative`, e um descendente
     absoluto escapava do recorte e alargava a pagina; agora `relative`.
   - `CompaniesPage` (cartoes mobile): `grid-cols-3` com chips largos virou
     `flex flex-wrap`.
2. `rounded-2xl`/`rounded-xl` remanescentes trocados por tokens (`rounded-panel`,
   `rounded-control`) em `skeletons`, `states`, `ManualIntakePanel`, `SourceControlsPanel`,
   `SourceCreateForm`, `HomologationQueuePage`, `InboxPage`; `skeletons.test.tsx` ajustado.
3. `apps/web/package-lock.json` estava fora de sincronia para `npm ci` com npm 10 (Docker
   `node:22.14.0`, faltavam `@emnapi/core` e `@emnapi/runtime` do `oxide-wasm32-wasi`),
   quebrando o build da imagem `frontend`. Regenerado com `npm install --package-lock-only`
   em `node:22.14.0-alpine`; `npm ci` local segue verde.

## Foco e contraste

- FilterPill: as classes `focus-within:outline-3 outline-offset-3 outline-ink` do Tailwind v4
  geram o anel de 3px medido no teste; nada a corrigir.
- Contraste: varredura por script (cor computada do texto contra o fundo composto, 4.5:1,
  3:1 para texto grande) nas 8 telas de lista, sem violacoes. A varredura nao cobre
  estados `disabled`, hover nem imagens; nao substitui revisao humana.

## Pendencias

- Imagem de referencia (`docs/assets/`) segue ausente (nao versionada).
- Revisao visual humana dos screenshots contra os tracos de 4.1 (D9: sem baseline de pixel).
