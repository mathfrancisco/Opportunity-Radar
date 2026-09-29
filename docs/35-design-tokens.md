# Tokens de design

> Fonte de verdade de tokens e regras: [`DESIGN.md`](../DESIGN.md) (SPEC 46, card F46-01).
> Este documento é a **medição de contraste** e o registro de ajustes; os valores abaixo
> foram regenerados contra `apps/web/src/styles.css` e o teste `apps/web/src/styles.test.ts`
> falha se um par documentado cair abaixo de 4.5 (texto) ou 3 (controle).

Os tokens vivem em `apps/web/src/styles.css`, dentro de `@theme`, e o Tailwind gera a
utilidade correspondente a partir do nome: `--color-muted` vira `text-muted`,
`--color-danger-surface` vira `bg-danger-surface`.

O nome descreve o papel, não o tom. `text-muted` continua correto se o cinza mudar;
`text-[#6d827b]` só era correto enquanto ninguém revisasse o contraste.

## Superfícies e traços

| Token | Valor | Uso |
| --- | --- | --- |
| `canvas` | `#f4f4f5` | fundo do app e da sidebar |
| `surface` | `#ffffff` | painel, linha de tabela, campo, pílula |
| `raised` | `#ffffff` | compatibilidade; igual a `surface` |
| `panel` | `#fafafa` | cabeçalho de tabela, bloco de resumo |
| `line` | `#e4e4e7` | borda do painel, divisória de linha |
| `line-strong` | `#d4d4d8` | borda de pílula, botão outlined e chip |
| `divider` | `#ececee` | separador entre linhas de tabela e traço do esqueleto |
| `control-line` | `#8a8a8a` | borda de campo de texto e checkbox |
| `accent` | `#c2410c` | página atual, marca de ativo, sublinhado de link, anel sobre fundo escuro |
| `accent-ink` | `#c2410c` | texto/borda de página atual |
| `accent-surface` | `#fff1ea` | hover da página atual, aviso leve |
| `brand` | `#d7f06f` | logotipo (D13); não é acento de UI |

## Texto e ação

| Token | Valor | Uso |
| --- | --- | --- |
| `ink` | `#171717` | texto principal e fundo do botão primário |
| `ink-hover` | `#404040` | botão primário sob o cursor |
| `subtle` | `#525252` | texto secundário |
| `muted` | `#6b6b6b` | rótulo, dica e metadado |
| `neutral-ink` | `#404040` | texto de badge neutro |

## Tons semânticos

Cada tom tem superfície, traço e texto, para que um estado seja legível sem depender só da
cor de fundo. O matiz foi neutralizado no F46-01; as razões continuam >= 4.5.

| Estado | Superfície | Traço | Texto |
| --- | --- | --- | --- |
| Sucesso | `success-surface` `#eef4ec`, `success-surface-soft` `#f4f8f2`, `success-surface-strong` `#e0eede` | `success-line` `#a3c29a` | `success-ink` `#2f4a2a`, `success-ink-strong` `#1f5a35` |
| Atenção | `warning-surface` `#faf4e6`, `warning-surface-strong` `#f5ebc8` | `warning-line` `#dcc98e` | `warning-ink` `#6f5214`, `warning-ink-strong` `#7f5410` |
| Erro | `danger-surface` `#fbf1ef`, `danger-surface-strong` `#f7e2de` | `danger-line` `#e4c8c2` | `danger-ink` `#9b3e2e` |
| Informação | `info-surface` `#eef1f5` | — | `info-ink` `#48566a` |

## Contraste medido

Razão de contraste WCAG 2.x de cada par em uso, calculada sobre os valores de
`styles.css`. Alvo AA: 4.5 para texto normal, 3 para componente de interface (1.4.11).

| Texto | Fundo | Razão |
| --- | --- | ---: |
| `ink` | `canvas` | 16.31 |
| `ink` | `surface` | 17.93 |
| `ink` | `raised` | 17.93 |
| `ink` | `panel` | 17.18 |
| `subtle` | `surface` | 7.81 |
| `subtle` | `canvas` | 7.11 |
| `muted` | `surface` | 5.33 |
| `muted` | `canvas` | 4.85 |
| `muted` | `panel` | 5.11 |
| `neutral-ink` | `canvas` | 9.43 |
| `accent-ink` | `surface` | 5.18 |
| `accent-ink` | `canvas` | 4.71 |
| `success-ink` | `success-surface` | 8.80 |
| `success-ink` | `success-surface-soft` | 9.16 |
| `success-ink-strong` | `success-surface-strong` | 6.79 |
| `warning-ink` | `warning-surface` | 6.62 |
| `warning-ink-strong` | `warning-surface-strong` | 5.54 |
| `danger-ink` | `danger-surface` | 6.06 |
| `danger-ink` | `danger-surface-strong` | 5.41 |
| `info-ink` | `info-surface` | 6.59 |
| `surface` | `ink` | 17.93 |
| `surface` | `ink-hover` | 10.37 |
| `ink` | `brand` | 14.16 |

Componentes (mínimo 3):

| Traço | Fundo | Razão |
| --- | --- | ---: |
| `control-line` | `surface` | 3.45 |
| `accent` | `surface` | 5.18 |

`line-strong` (pílula com rótulo, ícone e chevron visíveis) não entra na tabela de
componentes: é decisão explícita e revisável (SPEC 46, R4).

## Escala de texto

O nome diz o papel; tamanho, entrelinha, espaçamento e peso vêm juntos, porque é assim que
a escolha é feita — ninguém decide `2.25rem`, decide "título de página".

| Token | Tamanho | Entrelinha | Espaçamento | Peso | Uso |
| --- | --- | --- | --- | --- | --- |
| `text-metric-lg` | 2.25rem | 1.1 | -0.03em | 600 | score no detalhe da oportunidade |
| `text-metric` | 1.875rem | 1.15 | -0.03em | 600 | número do tile da Visão geral |
| `text-metric-sm` | 1.5rem | 1.2 | -0.03em | 600 | score no cartão da Inbox |
| `text-section` | 1.125rem | 1.4 | — | 600 | título de seção |
| `text-body` | 1rem | 1.75 | — | — | texto corrido |
| `text-prose` | 0.875rem | 1.5 | — | — | resumo dentro de cartão |

`text-sm` e `text-xs` continuam vindo da escala do Tailwind: são rótulo, célula e legenda,
já eram uma escala declarada, e trocá-los por apelidos nossos moveria cem chamadas sem
mudar uma decisão.

## Forma e ritmo

| Token | Valor | Uso |
| --- | --- | --- |
| `radius-panel` | 1rem | painel de conteúdo |
| `radius-control` | 0.5rem | pílula, botão, campo |
| `radius-chip` | 0.375rem | chip e badge outlined |

Papéis de texto novos (F46-01): `text-page-title` (1.25rem / 1.75rem / 600 / -0.01em),
`text-body-sm` (0.875rem / 1.25rem / 400), `text-caption` (0.75rem / 1rem / 500).

## Ajustes registrados

F46-01 trocou os **valores** mantendo os nomes (SPEC 46, D2). Todo par medido acima passa;
nenhum precisou de escurecimento adicional além dos valores propostos na SPEC. O ajuste
anterior (`muted #6d827b` para `#61746e`, F15-01) foi superado pelo novo `muted #6b6b6b`.

## Como isso é mantido

`apps/web/src/styles.test.ts` lê `styles.css` e falha se algum par da tabela acima ficar
abaixo de 4.5 (texto) ou 3 (componente).

`eslint.config.js` recusa literal hexadecimal em `.ts` e `.tsx` com
`no-restricted-syntax`. A regra roda em `npm run check`, que o CI executa: uma cor nova
precisa virar token antes de entrar numa tela.
