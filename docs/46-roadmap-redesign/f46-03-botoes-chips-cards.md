# CARD F46-03 — Botões, chips e cartões

- **Status:** Concluído em 2026-09-29
- **Fase:** 46 — Redesenho da interface web
- **Depende de:** F46-01
- **Bloqueia:** F46-04 a F46-06
- **Origem:** [SPEC 46](../46-spec-redesign-ui.md), §4.3, §5, §9, D6

## Resultado

`Button`, `StatusBadge` e `Card` ganham o visual do redesenho, e `Chip` passa a existir como
peça própria; nenhuma tela muda de código.

## Contexto

Botões eram `rounded-xl` com anel de foco `accent`, o selo de estado era uma pílula
`rounded-full` e o cartão `rounded-2xl`.

## Escopo

- `Button`: primário escuro (`ink`), secundário outlined (`line-strong`, fundo `surface`),
  `radius-control`; tamanhos `md` (36px) e `sm` (32px); 44px abaixo de `md`. O anel de foco
  é o `:focus-visible` global (3px `ink`, offset 3px): o anel fica fora do botão, sobre a
  página clara, onde `ink` é a cor que contrasta.
- `Chip`: outlined, `radius-chip`, `text-caption`, ponto de cor opcional (`dot`). Prop
  `tone` substitui o tom padrão (não empilha classes de cor).
- `StatusBadge`: renderiza `Chip`; **mesma API** (`value`, `labels`, `tones`, `absent`);
  ausência continua tracejada, estado sem rótulo mostra o próprio código.
- `Card`: borda `line`, `radius-control`, sem sombra; `interactive` inalterado.

## Fora de escopo

- `FilterPill`, `SearchInput`, `DataTable`, `Pagination` (F46-04 a F46-06).
- Trocar `bg-ink` do `Toolbar` (visual de pílula fica para quando as telas migrarem).
- Ponto de cor ligado por padrão no `StatusBadge` (API preservada; sem `dot` hoje).

## Critérios de aceite

- [x] Variantes primary/secondary, `sm` de 32px, raio de controle (`Button.test.tsx`).
- [x] `Chip` outlined, `tone` substitui, `dot` opcional e `aria-hidden` (`Chip.test.tsx`).
- [x] `StatusBadge` com a mesma API, testes existentes verdes (`StatusBadge.test.tsx`).
- [x] `Card` com borda `line`, `radius-control`, sem sombra (`Card.test.tsx`).
- [x] Nenhum hexadecimal em `.ts/.tsx`; seletores de rota/E2E inalterados.

## Verificação

`cd apps/web && npm run check` verde em 2026-09-29.

## Arquivos

- `apps/web/src/components/Button.tsx`, `Chip.tsx`, `StatusBadge.tsx`, `Card.tsx`
- `apps/web/src/components/Button.test.tsx`, `Chip.test.tsx`, `StatusBadge.test.tsx`,
  `Card.test.tsx`
