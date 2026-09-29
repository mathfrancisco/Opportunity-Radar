# CARD F46-04 — DataTable e células

- **Status:** Concluído em 2026-09-29
- **Fase:** 46 — Redesenho da interface web
- **Depende de:** F46-01, F46-03
- **Bloqueia:** F46-07, F46-08
- **Origem:** [SPEC 46](../46-spec-redesign-ui.md), §4.1, §4.3, §5, §9, §11

## Resultado

`DataTable` ganha o visual do redesenho e `cells.tsx` traz as peças de célula; os
consumidores atuais (Visão geral, Fontes, detalhe) mudam só de aparência.

## Contexto

O cabeçalho era `text-overline uppercase` sobre `canvas`, sem borda no contêiner, e o
esqueleto de tabela usava `rounded-2xl` e linhas de altura livre.

## Escopo

- `DataTable`: contêiner com borda `line` e `radius-control` que rola dentro de si;
  cabeçalho `panel`, `text-caption` `muted`, sem caixa alta; `th scope="col"`; `caption`
  `sr-only`; células com altura mínima de 44px (`h-11` na `td`, que a tabela trata como
  mínimo) e divisória `line`; primeira coluna fixa opcional mantida (`bg-surface` no corpo,
  `bg-panel` no cabeçalho).
- `selectable` opt-in: coluna inicial com checkbox rotulado "Selecionar todas"
  (`selectAllLabel`), `allSelected`/`someSelected` (indeterminado via propriedade DOM) e
  `onToggleAll`. `RowSelect` é o checkbox de linha, com rótulo obrigatório. Nenhuma tela o
  liga (SPEC 6).
- `cells.tsx`: `PrimaryText` (negrito `ink`), `SecondaryText` (`text-caption` `muted`),
  `DateTimeCell` (data `ink` + hora `muted`, `<time dateTime>`, pt-BR, `timeZone` opcional,
  substituto para data inválida) e `Avatar` (iniciais, decorativo, `rounded-full`).
- `TableSkeleton`: raio de controle, cabeçalho `panel` e linhas de 44px (`h-11`), para o
  conteúdo não pular ao chegar (F15-09).

## Fora de escopo

- Migrar telas (F46-07/08); ligar `selectable`; ação em lote.
- Chip outlined já entregue no F46-03.

## Critérios de aceite

- [x] Contêiner com borda/raio e rolagem interna; cabeçalho `panel`, `caption`, sem
      `uppercase` (`DataTable.test.tsx`).
- [x] Linha de 44px e divisória `line` por classe (`DataTable.test.tsx`).
- [x] `th scope="col"`, `caption` `sr-only`, primeira coluna fixa (testes existentes).
- [x] `selectable` só com opt-in; "Selecionar todas" rotulado; indeterminado; `RowSelect`
      rotulado.
- [x] `PrimaryText`, `SecondaryText`, `DateTimeCell`, `Avatar` (`cells.test.tsx`).
- [x] Esqueleto com a altura de linha nova; `skeletons.test.tsx` verde.
- [x] Nenhum hexadecimal em `.ts/.tsx`.

## Verificação

`cd apps/web && npm run check` verde em 2026-09-29 (219 testes).

## Arquivos

- `apps/web/src/components/DataTable.tsx`, `DataTable.test.tsx`
- `apps/web/src/components/cells.tsx`, `cells.test.tsx`
- `apps/web/src/components/skeletons.tsx`
