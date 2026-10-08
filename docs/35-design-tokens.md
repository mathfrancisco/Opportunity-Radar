# Tokens de design

> Fonte de verdade de tokens e regras: [`DESIGN.md`](../DESIGN.md) (SPEC 54, WP3).
> Este documento é a **medição de contraste** e o registro de ajustes; os valores abaixo
> foram regenerados contra `apps/web/src/styles.css` e o teste `apps/web/src/styles.test.ts`
> falha se um par documentado cair abaixo de 4.5 (texto) ou 3 (controle).

Os tokens vivem em `apps/web/src/styles.css`, dentro de `@theme`, e o Tailwind gera a
utilidade correspondente a partir do nome: `--color-muted` vira `text-muted`,
`--color-danger-surface` vira `bg-danger-surface`.

O nome descreve o papel, não o tom. `text-muted` continua correto se o cinza mudar;
`text-[#52626a]` só era correto enquanto ninguém revisasse o contraste.

## Superfícies e traços

| Token | Valor | Uso |
| --- | --- | --- |
| `canvas` | `#f7f8f8` | fundo do app |
| `surface` | `#ffffff` | painel, linha de tabela, campo, item atual da sidebar |
| `raised` | `#ffffff` | compatibilidade; igual a `surface` |
| `panel` | `#f1f5f5` | cabeçalho de tabela, bloco de resumo |
| `sidebar` | `#eef3f3` | fundo da sidebar e da barra do menu móvel |
| `line` | `#cbd7d8` | borda estrutural silenciosa de painel |
| `line-strong` | `#9fb2b4` | borda de botão outlined, pílula, chip e divisão da sidebar |
| `divider` | `#dde7e7` | separador entre linhas de tabela e traço do esqueleto |
| `control-line` | `#71878a` | borda de campo de texto e checkbox |
| `accent` | `#0b5d66` | ação primária, foco, marcador do item atual, sublinhado de link |
| `accent-hover` | `#084b52` | ação primária sob o cursor |
| `accent-ink` | `#0b5d66` | texto de link e de item atual |
| `accent-surface` | `#edf5f4` | seleção, contexto, hover leve |
| `brand` | `#0b5d66` | fundo do logotipo; glifo em `surface` |

## Texto e ação

| Token | Valor | Uso |
| --- | --- | --- |
| `ink` | `#132229` | texto principal |
| `ink-hover` | `#2a3b42` | `ink` sob o cursor, quando é fundo |
| `subtle` | `#405159` | texto secundário, item de navegação |
| `muted` | `#52626a` | rótulo, dica e metadado |
| `neutral-ink` | `#405159` | texto de badge neutro |

## Tons semânticos

Cada tom tem superfície, traço e texto, para que um estado seja legível sem depender só da
cor de fundo.

| Estado | Superfície | Traço | Texto |
| --- | --- | --- | --- |
| Sucesso | `success-surface` `#e3f1ed`, `success-surface-soft` `#eef7f4`, `success-surface-strong` `#d3e9e1` | `success-line` `#8fbfae` | `success-ink` `#14553c`, `success-ink-strong` `#0f4a33` |
| Atenção | `warning-surface` `#fdf3e9`, `warning-surface-strong` `#f5eadc` | `warning-line` `#e9c89d` | `warning-ink` `#704015`, `warning-ink-strong` `#854312` |
| Erro | `danger-surface` `#fbeeee`, `danger-surface-strong` `#f7e4e4` | `danger-line` `#e2b8b8` | `danger-ink` `#8c3030` |
| Informação | `info-surface` `#edf5f4` | — | `info-ink` `#314a4d` |

## Contraste medido

Razão de contraste WCAG 2.x de cada par em uso, calculada pela mesma fórmula de
`styles.test.ts` sobre os valores de `styles.css`. Alvo AA: 4.5 para texto normal, 3 para
componente de interface (1.4.11).

| Texto | Fundo | Razão |
| --- | --- | ---: |
| `ink` | `canvas` | 15.32 |
| `ink` | `surface` | 16.30 |
| `ink` | `raised` | 16.30 |
| `ink` | `panel` | 14.84 |
| `ink` | `sidebar` | 14.55 |
| `ink` | `accent-surface` | 14.72 |
| `subtle` | `surface` | 8.27 |
| `subtle` | `canvas` | 7.77 |
| `subtle` | `panel` | 7.53 |
| `subtle` | `sidebar` | 7.38 |
| `muted` | `surface` | 6.34 |
| `muted` | `canvas` | 5.96 |
| `muted` | `panel` | 5.77 |
| `muted` | `sidebar` | 5.66 |
| `muted` | `accent-surface` | 5.72 |
| `neutral-ink` | `canvas` | 7.77 |
| `neutral-ink` | `surface` | 8.27 |
| `accent-ink` | `surface` | 7.58 |
| `accent-ink` | `canvas` | 7.12 |
| `accent-ink` | `panel` | 6.90 |
| `accent-ink` | `sidebar` | 6.76 |
| `accent-ink` | `accent-surface` | 6.84 |
| `success-ink` | `success-surface` | 7.55 |
| `success-ink` | `success-surface-soft` | 8.04 |
| `success-ink-strong` | `success-surface-strong` | 8.06 |
| `warning-ink` | `warning-surface` | 7.88 |
| `warning-ink-strong` | `warning-surface-strong` | 6.30 |
| `danger-ink` | `danger-surface` | 7.19 |
| `danger-ink` | `danger-surface-strong` | 6.65 |
| `info-ink` | `info-surface` | 8.55 |
| `surface` | `accent` (botão primário, logotipo via `brand`) | 7.58 |
| `surface` | `accent-hover` (botão primário em hover) | 9.82 |
| `surface` | `brand` (glifo do logotipo) | 7.58 |
| `surface` | `ink` | 16.30 |
| `surface` | `ink-hover` | 11.65 |

Componentes e anel de foco (mínimo 3):

| Traço | Fundo | Razão |
| --- | --- | ---: |
| `control-line` | `surface` | 3.79 |
| `control-line` | `canvas` | 3.57 |
| `ink` | `surface` | 16.30 |
| `accent` (anel de foco) | `canvas` | 7.12 |
| `accent` (anel de foco) | `surface` | 7.58 |
| `accent` (anel de foco) | `panel` | 6.90 |
| `accent` (anel de foco) | `sidebar` | 6.76 |
| `accent` (anel de foco) | `accent-surface` | 6.84 |
| `accent-hover` | `surface` | 9.82 |

`line` e `line-strong` não entram na tabela de componentes: `line` é borda estrutural
decorativa; `line-strong` contorna botão e pílula que têm rótulo, ícone e chevron visíveis,
decisão explícita e revisável. Quem precisa de borda de componente usa `control-line`.

## Escala de texto

O nome diz o papel; tamanho, entrelinha, espaçamento e peso vêm juntos, porque é assim que
a escolha é feita — ninguém decide `2.25rem`, decide "título de página". Os papéis
`text-metric*` usam algarismos tabulares (`font-variant-numeric: tabular-nums`).

| Token | Tamanho | Entrelinha | Espaçamento | Peso | Uso |
| --- | --- | --- | --- | --- | --- |
| `text-metric-lg` | 2.25rem | 1.1 | -0.03em | 600 | score no detalhe da oportunidade |
| `text-metric` | 1.875rem | 1.15 | -0.03em | 600 | número do tile da Visão geral |
| `text-metric-sm` | 1.5rem | 1.2 | -0.03em | 600 | score no cartão da Inbox |
| `text-page-title` | 1.5rem | 2rem | -0.02em | 600 | título de página |
| `text-section` | 1.125rem | 1.4 | — | 600 | título de seção |
| `text-body` | 1rem | 1.75 | — | — | texto corrido |
| `text-prose` | 0.875rem | 1.5 | — | — | resumo dentro de cartão |
| `text-body-sm` | 0.875rem | 1.25rem | — | 400 | célula, corpo, subtítulo |
| `text-caption` | 0.75rem | 1rem | — | 500 | grupo da sidebar, chip, metadado |

`text-sm` e `text-xs` continuam vindo da escala do Tailwind.

## Forma e ritmo

| Token | Valor | Uso |
| --- | --- | --- |
| `radius-panel` | 0.5rem | painel de conteúdo |
| `radius-control` | 0.375rem | botão, campo, pílula |
| `radius-chip` | 0.25rem | chip e badge outlined |
| `shadow-overlay` | `0 4px 12px rgb(19 34 41 / 0.12)` | única sombra: gaveta e menu sobrepostos |

## Foco e movimento

`:focus-visible` desenha anel de 3px em `accent` com offset de 3px, fora do elemento. Por
isso ele continua visível ao redor de um botão petróleo: o contraste exigido é com o fundo
atrás do anel (tabela de componentes acima). `prefers-reduced-motion: reduce` reduz
animação e transição a 0.01ms globalmente.

## Ajustes registrados

SPEC 54 (WP3 A) trocou os **valores** mantendo os nomes (DESIGN.md, regra 8); `sidebar`,
`accent-hover` e `shadow-overlay` são os únicos tokens novos. Todo valor-alvo do protótipo
aceito passou sem ajuste. Escolha de traços: `line` `#cbd7d8` (o protótipo usa `#6f8588`,
que deixaria toda borda pesada nas telas atuais) e `line-strong` `#9fb2b4`. `info-surface` e
`accent-surface` compartilham `#edf5f4`. O ajuste anterior de `muted` (F15-01, F46-01) foi
superado pelo valor atual.

## Como isso é mantido

`apps/web/src/styles.test.ts` lê `styles.css` e falha se algum par da tabela acima ficar
abaixo de 4.5 (texto) ou 3 (componente), e se o anel de foco deixar de usar `accent` ou a
regra de movimento reduzido sumir.

`eslint.config.js` recusa literal hexadecimal em `.ts` e `.tsx` com
`no-restricted-syntax`. A regra roda em `npm run check`, que o CI executa: uma cor nova
precisa virar token antes de entrar numa tela.
