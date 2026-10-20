# Tokens de design

> Fonte de verdade de tokens e regras: [`DESIGN.md`](../DESIGN.md) (marca Bateia, §2, §3 e §7).
> Este documento é a **medição de contraste** e o registro de ajustes; os valores abaixo
> foram regenerados contra `apps/web/src/styles.css` e o teste `apps/web/src/styles.test.ts`
> falha se um par documentado cair abaixo de 4.5 (texto) ou 3 (controle), nos dois temas.

Os tokens vivem em `apps/web/src/styles.css`, dentro de `@theme` (tema claro, o padrão), e o
Tailwind gera a utilidade correspondente a partir do nome: `--color-muted` vira `text-muted`,
`--color-nugget-surface` vira `bg-nugget-surface`. O tema escuro redefine as mesmas
propriedades `--color-*` em dois blocos fora de `@theme`, depois dele:
`@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }` e
`:root[data-theme="dark"] { … }`. Os dois têm valores idênticos (o teste compara) e declaram
`color-scheme: dark`.

O nome descreve o papel, não o tom. `text-muted` continua correto se o cinza mudar.

## Superfícies, traços e acento

| Token | Claro | Escuro | Uso |
| --- | --- | --- | --- |
| `canvas` | `#ECEEEA` | `#0E1412` | fundo do app |
| `surface` | `#FAFBF8` | `#161E1B` | painel, linha de tabela, campo, item atual, texto sobre `accent` |
| `raised` | `#FAFBF8` | `#1B2521` | compatibilidade; no escuro, um degrau acima de `surface` |
| `panel` | `#F1F3EF` | `#1A2420` | cabeçalho de tabela, bloco de resumo |
| `sidebar` | `#E4E8E2` | `#111816` | fundo da sidebar e da barra do menu móvel |
| `line` | `#CBD2CA` | `#2A3631` | borda estrutural silenciosa de painel |
| `line-strong` | `#A3ADA5` | `#3E4C46` | borda de botão outlined, pílula, chip |
| `divider` | `#DCE1DA` | `#222D29` | separador entre linhas de tabela |
| `control-line` | `#6F7B74` | `#6E7D76` | borda de campo de texto e checkbox |
| `accent` | `#1E5B4B` | `#79C2A6` | ação primária, foco, item atual, link (verde-rio) |
| `accent-hover` | `#16483B` | `#93D0B8` | ação primária sob o cursor |
| `accent-ink` | `#1E5B4B` | `#79C2A6` | texto de link e de item atual |
| `accent-surface` | `#E2EEE8` | `#1C2E28` | seleção, contexto, hover leve |
| `brand` | `#1E5B4B` | `#79C2A6` | fundo do ícone; anéis do logo |
| `nugget` | `#A87A12` | `#E2B54D` | pepita preenchida do match, ponto do logo (não é texto) |
| `nugget-ink` | `#7D5508` | `#E9C46A` | texto do veredito Alta prioridade |
| `nugget-surface` | `#F6EBCF` | `#2E2814` | fundo do veredito Alta prioridade |

O dourado (`nugget*`) só aparece em pepitas do match, ponto do logo e veredito Alta prioridade.

## Texto e ação

| Token | Claro | Escuro | Uso |
| --- | --- | --- | --- |
| `ink` | `#18221E` | `#E4EAE5` | texto principal |
| `ink-hover` | `#2B3732` | `#C9D2CC` | `ink` sob o cursor, quando é fundo |
| `subtle` | `#3F4B45` | `#B4C0B9` | texto secundário, item de navegação |
| `muted` | `#55625B` | `#98A69E` | rótulo, dica e metadado |
| `neutral-ink` | `#3F4B45` | `#B4C0B9` | texto de badge neutro |

## Tons semânticos

Cada tom tem superfície, traço e texto, para que um estado seja legível sem depender só da
cor de fundo. Valores no formato claro / escuro.

| Estado | Superfície | Traço | Texto |
| --- | --- | --- | --- |
| Sucesso | `success-surface` `#E6F0DF` / `#1B2A17`, `success-surface-soft` `#EEF5E9` / `#17241A`, `success-surface-strong` `#D8E8CD` / `#22351D` | `success-line` `#A6C597` / `#4C6E3E` | `success-ink` `#2D5A1E` / `#A9D38F`, `success-ink-strong` `#244A17` / `#BFE0A8` |
| Atenção | `warning-surface` `#F7E9DA` / `#33231A`, `warning-surface-strong` `#F1DEC8` / `#3D2A1E` | `warning-line` `#DDB58E` / `#7A5233` | `warning-ink` `#7A3E10` / `#F0B07F`, `warning-ink-strong` `#6B360D` / `#F5C39C` |
| Erro | `danger-surface` `#F8E6E3` / `#351C1A`, `danger-surface-strong` `#F3DAD6` / `#40221F` | `danger-line` `#DDAFA8` / `#7D3F38` | `danger-ink` `#8A2E25` / `#F2A39A` |
| Informação | `info-surface` `#E4ECEE` / `#1A2A2E` | — | `info-ink` `#2F4A52` / `#A7C8D0` |

## Contraste medido

Razão de contraste WCAG 2.x de cada par em uso, calculada pela mesma fórmula de
`styles.test.ts` sobre os valores de `styles.css`. Alvo AA: 4.5 para texto normal, 3 para
componente de interface (1.4.11).

| Texto | Fundo | Claro | Escuro |
| --- | --- | ---: | ---: |
| `ink` | `sidebar` | 13.17 | 14.75 |
| `subtle` | `sidebar` | 7.35 | 9.59 |
| `muted` | `sidebar` | 5.16 | 7.10 |
| `accent-ink` | `sidebar` | 6.38 | 8.64 |
| `subtle` | `panel` | 8.16 | 8.49 |
| `accent-ink` | `panel` | 7.09 | 7.65 |
| `accent-ink` | `accent-surface` | 6.64 | 6.85 |
| `ink` | `accent-surface` | 13.70 | 11.69 |
| `muted` | `accent-surface` | 5.37 | 5.63 |
| `neutral-ink` | `surface` | 8.78 | 9.05 |
| `ink` | `canvas` | 13.98 | 15.25 |
| `ink` | `surface` | 15.72 | 13.92 |
| `ink` | `raised` | 15.72 | 12.90 |
| `ink` | `panel` | 14.62 | 13.06 |
| `subtle` | `surface` | 8.78 | 9.05 |
| `subtle` | `canvas` | 7.81 | 9.92 |
| `muted` | `surface` | 6.16 | 6.70 |
| `muted` | `canvas` | 5.48 | 7.35 |
| `muted` | `panel` | 5.73 | 6.29 |
| `neutral-ink` | `canvas` | 7.81 | 9.92 |
| `accent-ink` | `surface` | 7.62 | 8.16 |
| `accent-ink` | `canvas` | 6.78 | 8.94 |
| `success-ink` | `success-surface` | 6.90 | 8.92 |
| `success-ink` | `success-surface-soft` | 7.28 | 9.51 |
| `success-ink-strong` | `success-surface-strong` | 7.91 | 9.06 |
| `warning-ink` | `warning-surface` | 6.98 | 8.04 |
| `warning-ink-strong` | `warning-surface-strong` | 7.42 | 8.50 |
| `danger-ink` | `danger-surface` | 6.97 | 7.87 |
| `danger-ink` | `danger-surface-strong` | 6.33 | 7.15 |
| `info-ink` | `info-surface` | 7.89 | 8.35 |
| `surface` | `ink` | 15.72 | 13.92 |
| `surface` | `ink-hover` | 11.93 | 10.99 |
| `surface` | `accent` | 7.62 | 8.16 |
| `surface` | `accent-hover` | 9.99 | 9.68 |
| `surface` | `brand` | 7.62 | 8.16 |
| `nugget-ink` | `nugget-surface` | 5.58 | 8.79 |
| `nugget-ink` | `surface` | 6.37 | 10.17 |
| `nugget-ink` | `canvas` | 5.66 | 11.15 |

Componentes e anel de foco (mínimo 3; o anel de foco usa `accent`):

| Traço | Fundo | Claro | Escuro |
| --- | --- | ---: | ---: |
| `control-line` | `surface` | 4.25 | 3.93 |
| `control-line` | `canvas` | 3.78 | 4.31 |
| `accent` | `surface` | 7.62 | 8.16 |
| `ink` | `surface` | 15.72 | 13.92 |
| `accent` | `canvas` | 6.78 | 8.94 |
| `accent` | `panel` | 7.09 | 7.65 |
| `accent` | `sidebar` | 6.38 | 8.64 |
| `accent` | `accent-surface` | 6.64 | 6.85 |
| `accent-hover` | `surface` | 9.99 | 9.68 |
| `nugget` | `surface` | 3.70 | 8.86 |
| `nugget` | `canvas` | 3.30 | 9.71 |

`line` e `line-strong` não entram na tabela de componentes: `line` é borda estrutural
decorativa; `line-strong` contorna botão e pílula que têm rótulo, ícone e chevron visíveis,
decisão explícita e revisável. Quem precisa de borda de componente usa `control-line`.

## Escala de texto

O nome diz o papel; tamanho, entrelinha, espaçamento e peso vêm juntos. Os papéis
`text-metric*` usam algarismos tabulares (`font-variant-numeric: tabular-nums`).

| Token | Tamanho | Entrelinha | Espaçamento | Peso | Uso |
| --- | --- | --- | --- | --- | --- |
| `text-metric-lg` | 2.25rem | 1.1 | -0.03em | 600 | score no detalhe da oportunidade |
| `text-metric` | 1.875rem | 1.15 | -0.03em | 600 | número do tile da Visão geral |
| `text-metric-sm` | 1.5rem | 1.2 | -0.03em | 600 | score no cartão da Inbox |
| `text-page-title` | 1.75rem | 2.25rem | -0.01em | 400 | título de página (com `font-display`) |
| `text-section` | 1.125rem | 1.4 | — | 600 | título de seção |
| `text-body` | 1rem | 1.65 | — | — | texto corrido |
| `text-prose` | 0.875rem | 1.5 | — | — | resumo dentro de cartão |
| `text-body-sm` | 0.875rem | 1.25rem | — | 400 | célula, corpo, subtítulo |
| `text-caption` | 0.75rem | 1rem | — | 500 | grupo da sidebar, chip, metadado |

`text-sm` e `text-xs` continuam vindo da escala do Tailwind.

## Forma, fontes e ritmo

| Token | Valor | Uso |
| --- | --- | --- |
| `radius-panel` | 0.75rem | painel de conteúdo |
| `radius-control` | 0.5rem | botão, campo, item da sidebar |
| `radius-chip` | 999px | chip, veredito e filtro |
| `shadow-overlay` | `0 4px 16px rgb(14 20 18 / 0.16)` | única sombra: gaveta e menu sobrepostos |
| `font-sans` | Schibsted Grotesk variável + `system-ui` | interface, corpo, números |
| `font-display` | Young Serif + `Georgia, serif` | título de página, wordmark |

Fontes auto-hospedadas por `@font-face` em `styles.css` (pacotes
`@fontsource-variable/schibsted-grotesk` e `@fontsource/young-serif`, subset latin,
`font-display: swap`); Inter foi removida.

## Foco e movimento

`:focus-visible` desenha anel de 3px em `accent` (verde-rio) com offset de 3px, fora do
elemento. Por isso ele continua visível ao redor de um botão verde-rio: o contraste exigido é
com o fundo atrás do anel (tabela de componentes acima). `prefers-reduced-motion: reduce`
reduz animação e transição a 0.01ms globalmente.

## Ajustes registrados

- Marca Bateia: os **valores** mudaram mantendo os nomes (DESIGN.md, regra 8); `nugget`,
  `nugget-ink`, `nugget-surface` e `font-display` são os tokens novos, e o tema escuro é novo.
- Dourado claro escurecido de `#C8961E` para `#A87A12` para chegar a 3:1 sobre `canvas`
  (3.30 medido; `#C8961E` não chegava).

## Como isso é mantido

`apps/web/src/styles.test.ts` lê `styles.css` e falha se algum par da tabela acima ficar
abaixo de 4.5 (texto) ou 3 (componente) em qualquer tema, se os dois blocos escuros divergirem,
e se o anel de foco deixar de usar `accent` ou a regra de movimento reduzido sumir.

`eslint.config.js` recusa literal hexadecimal em `.ts` e `.tsx` com
`no-restricted-syntax`. A regra roda em `npm run check`, que o CI executa: uma cor nova
precisa virar token antes de entrar numa tela.
