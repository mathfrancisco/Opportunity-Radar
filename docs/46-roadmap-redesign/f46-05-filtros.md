# CARD F46-05 — FilterPill, SearchInput e FilterBar

- **Status:** Concluído em 2026-09-29
- **Fase:** 46 — Redesenho da interface web
- **Depende de:** F46-01, F46-03
- **Bloqueia:** F46-07, F46-08
- **Origem:** [SPEC 46](../46-spec-redesign-ui.md), §5, §7, §9, §10, D3, D11, D12

## Resultado

Três componentes novos para a linha de filtros, com teste e sem uso em tela: as rotas
continuam com `SearchBar` e `Toolbar` até F46-07/08.

## Contexto

Hoje a Inbox usa cinco `<select>` em grade e `SearchBar` (campo + botão "Buscar" visível).

## Escopo

- `FilterPill`: `<label>` visível ligado por `htmlFor` a um `<select>` nativo estilizado
  (`appearance-none`), ícone decorativo à esquerda (funil por padrão, `icon` opcional) e
  chevron à direita, ambos `aria-hidden`. Ativa (`data-active`, borda `ink`, rótulo em
  negrito) quando `value` difere de `defaultValue` (padrão `''`); inativa usa `line-strong`.
  `getByLabel` continua funcionando. 44px abaixo de `md`.
- `SearchInput`: `<form role="search">`, campo rotulado (`label` `sr-only`), lupa que é o
  botão de envio, nomeada "Buscar" por texto `sr-only` (D11). Enter envia; `onSubmit()`
  não recebe evento e o recarregamento já é impedido. `type="search"`, borda `control-line`,
  ~20rem em `md+`, largura total abaixo.
- `FilterBar`: `flex-wrap`; pílulas em `role="group"` (`label`, padrão "Filtros") à
  esquerda; slot `search` à direita (`md:ml-auto`), linha própria em largura total abaixo
  de `md`.
- `icons.tsx`: `SearchIcon`, `ChevronDownIcon`, `FilterIcon`.

## Fora de escopo

- Dropdown "Buscas salvas"/"Salvar busca" (D12): sem UI aqui, integrado no F46-07.
- Remover `SearchBar` (fica até as telas migrarem; F46-07/08 trocam e apagam).
- Estilizar a lista aberta do `<select>` (R2).

## Critérios de aceite

- [x] `FilterPill` com rótulo acessível, `onChange` e estado ativo só quando ≠ padrão.
- [x] `SearchInput` com `role="search"`, envio por Enter/lupa e botão "Buscar" `sr-only`.
- [x] `FilterBar` com quebra e busca em largura total abaixo de `md` (classes).
- [x] `SearchBar` e rotas existentes intactos e verdes.
- [x] Nenhum hexadecimal em `.ts/.tsx`.

## Verificação

`cd apps/web && npm run check` verde em 2026-09-29 (230 testes). Os testes dos três
componentes estão em `FilterPill.test.tsx`. jsdom não faz envio implícito por Enter: o teste
dispara o evento `submit` do formulário, que é o que o Enter provoca no navegador.

## Arquivos

- `apps/web/src/components/FilterPill.tsx`, `SearchInput.tsx`, `FilterBar.tsx`
- `apps/web/src/components/FilterPill.test.tsx`
- `apps/web/src/components/icons.tsx`
