# F46-08 - Fontes, Fila de homologacao e Empresas

Fonte: `docs/46-spec-redesign-ui.md` (6, 7, 9-11, D8); achados D8 em `f46-06-paginacao.md`.

## Entregue

- `PageShell`/`AppShell`: prop opcional `actions`, repassada ao `PageHeader` (sem ela nada
  muda).
- `SourcesPage`: cada fonte e uma linha de `DataTable` (Fonte, Estado, Ultima execucao,
  Itens, Agendamento, Acoes). Nome em negrito com o tipo em texto secundario; estado da
  ultima execucao como chip (`StatusBadge`); habilitacao/evidencia/termos em texto
  secundario. "Adicionar fonte" (antes "Nova fonte") foi para `PageHeader.actions`, botao
  secundario, e some enquanto o formulario de criacao esta aberto. "Executar agora",
  "Homologacao" e "Ver execucoes" sao botoes secundarios `sm` por linha. Painel de
  homologacao, registro manual e historico de execucoes abrem numa linha de largura total
  logo abaixo da fonte. Resultado/erro da execucao fica na celula do nome. Link "Fila de
  homologacao" continua no corpo (o cabecalho aceita uma acao so).
- `HomologationQueue` (modo lista): `DataTable` com `RowSelect` por linha (sem "selecionar
  todas"), nome + tipo, chip de estado e botao `sm` "Homologar", que abre o modo
  sequencial ja naquela proposta. Resultado da sonda em lote continua na linha
  (`role="status"`).
- `CompaniesPage`: `DataTable` a partir de `md`, cartoes (`Card`) abaixo, como a Inbox;
  prioridade, status e verificacao como `Chip`; fontes em cinza; busca vira `SearchInput`
  dentro de `FilterBar`. `Pagination` + `PageSizeSelect` (10/25/50/100, padrao 25, maximo da
  API 100). O estado continua local (a tela nunca usou URL): buscar ou trocar o tamanho
  volta para a pagina 1.
- `SearchBar.tsx` removido (nenhum uso restante; nao tinha teste proprio).

## E2E

`tests/e2e/browser/specs/01-happy-path.spec.ts` e `02-failure-scenarios.spec.ts`: o
localizador `page.locator('article', { hasText: <fonte> })` passou a
`page.locator('tr', { hasText: <fonte> })`, porque a fonte deixou de ser um `<article>`. O
botao "Executar agora" e o texto `Execucao SUCCEEDED` seguem na mesma linha.

## Testes

- Ajustados por forma: `SourcesPage.test.tsx` (tipo sem parenteses; contagem por
  `tbody tr`), `HomologationQueue.test.tsx` (`li` para `tbody tr`).
- Novos: `PageShell` (`actions`), `SourcesPage` (3: acao de cabecalho, celulas, linha do
  historico), `HomologationQueue` (1), `CompaniesPage.test.tsx` (5: tabela/chips, busca,
  paginacao, tamanho, cartoes).
- `cd apps/web && npm run check` verde: 263 testes.
