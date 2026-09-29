# F46-09 - Telas restantes e remocao de tokens obsoletos

Fonte: `docs/46-spec-redesign-ui.md` (6, 9-11); `DESIGN.md`.

## Entregue

- `Toolbar`: visual de pilula (grupo com borda `line-strong`, opcao ativa em `canvas` com
  peso 600 e `aria-pressed`); acabou o bloco `bg-ink`. Continua `role="group"` nomeado.
- `OverviewPage`: tiles com borda e sem sombra; "Metricas operacionais por fonte" em
  `DataTable` (a tabela cuida de padding e divisorias), `Toolbar` de janela como pilula a
  direita do titulo; "Decisao de hoje" (contagem por veredito) e "Buscas salvas com
  novidade" viram tabela compacta; chip do breaker vira `Chip`.
- `OpportunityDetailPage` (estrutural): "Avaliar agora" foi para `PageHeader.actions`
  (secundario); fatos em `Card`; skills e veredito como `Chip`; filtros eliminatorios em
  `Card`; fatores seguem em `DataTable`. Link "voltar" ja ficava no topo.
- `CompanyDetailPage`: "Editar empresa" em `PageHeader.actions`; fatos em `Card`; aliases
  como `Chip`; "Ultimas vagas" em `DataTable` (Vaga, Modalidade, Decisao, Score).
- `PipelinePage`: colunas mantidas; cartoes com `Card` (borda `line`).
- `ProfilePage`: campos em `Field` + `controlClassName`; dicas viram `hint`.
- `StatusPage`: `.status` virou `Chip` com ponto, dentro de `div role="status"` (texto e
  papel iguais).
- `ApplicationPanel`, `AnalysisPanel`, `CompanyForm`, `CompanySourceForm`, `Field`:
  `rounded-2xl`/`rounded-xl` trocados por `rounded-control`.
- Removidos de `styles.css`: `text-display`, `text-display-lg`, `text-overline`,
  `radius-shell`, `shadow-shell`, `spacing-section`, `spacing-block`, `line-soft` e as
  classes `.status*`; `mt-section`/`mt-block` viraram `mt-10`/`mt-6`. `DESIGN.md` e
  `docs/35-design-tokens.md` atualizados.
- `f46-05-filtros.md` e `f46-07-inbox.md`: mencoes obsoletas a `SearchBar` corrigidas.

## E2E

Nenhum seletor mudou: `getByRole('button', { name: 'Avaliar agora' })` segue valido (o
botao so mudou de lugar).

## Testes

Formas ajustadas: nenhuma nos testes de rota. Novo: `Toolbar` (pilula, sem `bg-ink`).
`cd apps/web && npm run check` verde.
