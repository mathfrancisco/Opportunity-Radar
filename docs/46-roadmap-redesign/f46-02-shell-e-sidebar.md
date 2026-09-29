# CARD F46-02 — Shell e sidebar

- **Status:** Concluído em 2026-09-29
- **Fase:** 46 — Redesenho da interface web
- **Depende de:** F46-01
- **Bloqueia:** F46-07 a F46-10
- **Origem:** [SPEC 46](../46-spec-redesign-ui.md), §5, §6, §7, §9, §10, D4, D7, D10, D13

## Resultado

Toda tela passa a ter sidebar à esquerda (mesmos três grupos e sete itens de antes) e o
conteúdo num painel branco sem sombra, sem alterar nenhuma das 10 rotas: `PageShell` mantém
a API e delega para o novo `AppShell`.

## Contexto

A navegação era uma faixa horizontal no topo do cartão central, com título de 36 a 48px e
*eyebrow* acima dele.

## Escopo

- `Sidebar`: logotipo (`bg-brand`, D13) + `<nav aria-label="Navegação principal">` com os
  grupos "Dia a dia / Catálogo / Diagnóstico"; item ativo é pílula `surface` com borda
  `line` e `aria-current="page"`; ícone `aria-hidden`.
- `AppShell`: sidebar de 15rem fixa em `md+`; abaixo de `md`, barra com botão "Menu"
  (`aria-expanded`, `aria-controls`) que abre a gaveta; `Esc` fecha e devolve o foco ao
  botão; seguir um link ou clicar no fundo também fecha. Painel branco, `radius-panel`,
  borda `line`, sem sombra; sem raio externo e `p-4` abaixo de `md`.
- `PageHeader`: único `<h1>` (`text-page-title`), subtítulo e slot `actions`.
- `PageShell`: alias de `AppShell`; `current`, `title`, `description`, `children`, `footer`
  iguais; `eyebrow` opcional e não exibido (D10). `NavigationPath` segue exportado.
- Link "Pular para o conteúdo" continua o primeiro alvo de tabulação (fica antes do botão
  de menu e da sidebar).

## Fora de escopo

- Botões, chips e cartões (F46-03); tabelas, filtros e paginação (F46-04 a F46-06).
- Estado recolhido da sidebar, faixa de abas do navegador (D4, D15).
- Uso do slot `actions` pelas telas (F46-07 a F46-09).

## Decisões de implementação

- A gaveta é a própria `<aside>` com classe `hidden` fechada, então não recebe foco
  fechada; em jsdom (sem CSS) o teste verifica a classe e os atributos ARIA.
- O foco não é movido para dentro da gaveta ao abrir: o botão precede a gaveta na ordem do
  DOM, então o próximo `Tab` já a alcança.
- Alvo de toque: itens da sidebar e botão de menu têm 44px abaixo de `md`, 36px em `md+`.

## Critérios de aceite

- [x] Três grupos, sete itens, `aria-label="Navegação principal"`, um só `aria-current`.
- [x] Gaveta: `aria-expanded`/`aria-controls`, `Esc` fecha e devolve o foco.
- [x] Pular para o conteúdo é o primeiro alvo de tabulação.
- [x] API de `PageShell` preservada; `eyebrow` aceito e invisível.
- [x] Nenhum hexadecimal em `.ts/.tsx`; painel sem sombra.

## Verificação

`cd apps/web && npm run check` verde em 2026-09-29. Testes: `Sidebar.test.tsx`,
`AppShell.test.tsx`, `PageHeader.test.tsx`, `PageShell.test.tsx` (adaptado: item ativo agora
`bg-surface`). Screenshots em 1280 e 375 ficam para F46-10.

## Arquivos

- `apps/web/src/components/Sidebar.tsx`, `AppShell.tsx`, `PageHeader.tsx`, `PageShell.tsx`
- `apps/web/src/components/Sidebar.test.tsx`, `AppShell.test.tsx`, `PageHeader.test.tsx`,
  `PageShell.test.tsx`
