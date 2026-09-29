# CARD F46-06 — Pagination e PageSizeSelect

- **Status:** Concluído em 2026-09-29 (componentes); integração nas telas fica para F46-07/08
- **Fase:** 46 — Redesenho da interface web
- **Depende de:** F46-01, F46-03
- **Bloqueia:** F46-07, F46-08
- **Origem:** [SPEC 46](../46-spec-redesign-ui.md), §5, §7.5, §9, §11, D8

## Resultado

`Pagination` e `PageSizeSelect` existem com teste, sem uso em tela. A Inbox continua com
"Anterior/Próxima" até o F46-07.

## Contexto

A Inbox mostra "Página X de Y" com pageSize fixo 25; não há seletor de itens por página.

## Escopo

- `Pagination` (`page`, `pageSize`, `total`, `onPageChange`, `itemLabel`, `label`):
  `<nav aria-label="Paginação">`; "Exibindo X a Y de N {itemLabel}" em `<p aria-live="polite">`;
  botões numerados `aria-label="Página N"` com janela e elipse (`1 … 4 5 6 … 12`; até 7
  páginas mostra todas; uma elipse nunca esconde uma página só); atual com
  `aria-current="page"`, `border-accent text-accent-ink font-semibold`; anterior/próxima com
  `aria-label` "Página anterior"/"Próxima página", `disabled` nos limites; página fora do
  intervalo é corrigida; 0 itens mostra só "Nenhum resultado" (sem botões).
- `PageSizeSelect` (`id`, `value`, `onChange(number)`, `options`): rótulo visível "Itens por
  página" sobre `<select>` nativo; opções padrão 10/25/50/100.

## Achados D8 (verificados em 2026-09-29)

- **Inbox aceita tamanho variável.** `GET` da Inbox em
  `src/opportunity_radar/presentation/http/dashboard.py` (linhas 499-500) recebe
  `offset: int = Query(0, ge=0)` e `limit: int = Query(50, ge=1, le=200)`. O cliente
  (`apps/web/src/features/dashboard/api.ts`, ~l.317-339) já envia `offset=(page-1)*pageSize` e
  `limit=pageSize`; só a tela fixa `const pageSize = 25` (`InboxPage.tsx:27`). Portanto o
  `PageSizeSelect` **pode** ser integrado no F46-07, com opções até 200 (sugestão 10/25/50/100).
  Mudar o tamanho deve zerar `page` na URL (`?page=`).
- **Empresas já é paginada.** `GET /companies` (`companies.py` ~l.315-316) aceita
  `page` (>=1) e `page_size` (padrão 50, `le=100`); o cliente
  (`features/companies/api.ts:368-384`) envia ambos e a tela usa `pageSize = 25` com
  `totalPages`. Recebe `Pagination` nova no F46-08; `PageSizeSelect` aí só até 100.

## Fora de escopo

- Ligar nas telas (F46-07: Inbox; F46-08: Empresas) e ler/gravar `pageSize` na URL.
- Salto para página digitada.

## Critérios de aceite

- [x] "Exibindo 1 a 15 de 145 oportunidades", corte na última página, região `polite`.
- [x] Janela: poucas páginas, elipse dos dois lados, só de um lado nas pontas, sem elipse
      de uma página.
- [x] Atual com `aria-current="page"`, borda de acento e peso; só uma marcada.
- [x] Anterior desabilitado na 1ª e próxima na última; uma página; 0 itens.
- [x] Cliques pedem a página certa; página fora do intervalo é corrigida.
- [x] `PageSizeSelect` rotulado, avisa número, aceita opções.
- [x] Nenhum hexadecimal em `.ts/.tsx`.

## Verificação

`cd apps/web && npm run check` verde em 2026-09-29 (246 testes).

## Arquivos

- `apps/web/src/components/Pagination.tsx`, `PageSizeSelect.tsx`
- `apps/web/src/components/Pagination.test.tsx`
