# F46-07 - Inbox como tabela

Fonte: `docs/46-spec-redesign-ui.md` (6, 7, 9-11, D8, D11, D12).

## Entregue

- `InboxPage`: a partir de `md`, cada oportunidade e uma linha de `DataTable`
  (Oportunidade, Decisao, Score, Modalidade/Senioridade, Status, Publicada, Acoes).
  Titulo em link, "empresa · local" em texto secundario; `VerdictBadge`, chip
  "Possivel duplicata", selo `data-testid="startup-badge"`, candidatura, aviso de
  avaliacao antiga e analise semantica ficam na propria linha. Por linha:
  "Relevante" e "Nao e para mim" (`Button` sm).
- Abaixo de `md` continua a visao em cartoes (`useMediaQuery('(min-width: 768px)')`,
  `src/lib/useMediaQuery.ts`; sem `matchMedia`, como no jsdom, vale desktop). Um so
  layout e montado por vez, entao `getByRole`/`getByText` do E2E nao duplicam.
- Filtros: Decisao, Modalidade, Status, Senioridade, Ordenar por e Candidatura sao
  `FilterPill` na `FilterBar`; busca vira `SearchInput` (D11). Os campos numericos/texto
  (score minimo, remuneracao, fonte, pais) foram para `<details>` "Mais filtros" para
  nao perder funcao. Checkboxes e filtro de area ficam como estavam.
- "Buscas salvas" (D12): `SavedSearchesMenu`, botao com `aria-expanded`/`aria-controls`
  a direita da barra; abre a lista e o formulario "Salvar esta busca"; Esc fecha e
  devolve o foco; clique fora fecha; aplicar uma busca fecha o menu.
- `Pagination` + `PageSizeSelect` (10/25/50/100, padrao 25). `?page=` preservado;
  tamanho em `?size=` (ausente = 25). Trocar filtro ou tamanho volta para a pagina 1.
  `size` nao entra nas buscas salvas.
- `SearchBar.tsx` permaneceu nesta etapa (`CompaniesPage` ainda o usava); foi removido no F46-08.

## E2E

`tests/e2e/browser/specs` nao mudou: o link pelo titulo, o texto exato
`N oportunidade(s) encontrada(s).` e "Analise semantica indisponivel" continuam na tela.

## Testes

`InboxPage.test.tsx`: 12 existentes verdes sem alteracao + 8 novos (linha da tabela,
cartoes abaixo de md, paginacao/`?page=`, tamanho na URL, reset por filtro,
Candidatura como pill, menu de buscas salvas).
