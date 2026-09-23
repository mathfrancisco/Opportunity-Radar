# Tokens de design

Os tokens vivem em `apps/web/src/styles.css`, dentro de `@theme`, e o Tailwind gera a
utilidade correspondente a partir do nome: `--color-muted` vira `text-muted`,
`--color-danger-surface` vira `bg-danger-surface`.

O nome descreve o papel, não o tom. `text-muted` continua correto se o cinza mudar;
`text-[#6d827b]` só era correto enquanto ninguém revisasse o contraste.

## Superfícies e traços

| Token | Valor | Uso |
| --- | --- | --- |
| `canvas` | `#f2f5ef` | fundo da página e cabeçalho de tabela |
| `surface` | `#ffffff` | cartão, linha de tabela, campo |
| `raised` | `#fbfcf8` | barra de navegação do `PageShell` |
| `panel` | `#f7faf6` | painel de resumo dentro de uma tela |
| `line` | `#dce4dc` | borda padrão de cartão |
| `line-strong` | `#c8d4c8` | borda de controle e de estado vazio |
| `line-soft` | `#ced8ce` | borda da navegação |
| `divider` | `#e4ebe4` | separador entre linhas de tabela e traço do esqueleto de carregamento |
| `accent` | `#d7f06f` | sublinhado de link e anel de foco |

## Texto e ação

| Token | Valor | Uso |
| --- | --- | --- |
| `ink` | `#17322d` | texto principal e fundo do botão primário |
| `ink-hover` | `#25483f` | botão primário sob o cursor |
| `subtle` | `#547068` | texto secundário |
| `muted` | `#61746e` | rótulo, dica e metadado |
| `neutral-ink` | `#41594f` | texto de badge neutro |

## Tons semânticos

Cada tom tem superfície, traço e texto, para que um estado seja legível sem depender só da
cor de fundo.

| Estado | Superfície | Traço | Texto |
| --- | --- | --- | --- |
| Sucesso | `success-surface` `#eef6d8`, `success-surface-soft` `#f3f8e6`, `success-surface-strong` `#deefde` | `success-line` `#b6d36a` | `success-ink` `#42571c`, `success-ink-strong` `#216142` |
| Atenção | `warning-surface` `#fbf3e2`, `warning-surface-strong` `#f7edca` | `warning-line` `#e3cf9a` | `warning-ink` `#7a5a16`, `warning-ink-strong` `#8b5c13` |
| Erro | `danger-surface` `#fdf3f0`, `danger-surface-strong` `#f9e4df` | `danger-line` `#e8cfc6` | `danger-ink` `#9b3e2e` |
| Informação | `info-surface` `#eef3df` | — | `info-ink` `#5c694e` |

## Contraste medido

Razão de contraste WCAG de cada par texto/fundo em uso. O alvo é AA, 4.5 para texto normal.

| Texto | Fundo | Razão |
| --- | --- | ---: |
| `ink` | `canvas` | 12.47 |
| `ink` | `surface` | 13.72 |
| `ink` | `raised` | 13.32 |
| `ink` | `panel` | 13.04 |
| `subtle` | `surface` | 5.39 |
| `subtle` | `canvas` | 4.90 |
| `muted` | `surface` | 4.96 |
| `muted` | `canvas` | 4.51 |
| `muted` | `panel` | 4.72 |
| `neutral-ink` | `canvas` | 6.90 |
| `success-ink` | `success-surface` | 7.20 |
| `success-ink` | `success-surface-soft` | 7.42 |
| `success-ink-strong` | `success-surface-strong` | 6.14 |
| `warning-ink` | `warning-surface` | 5.76 |
| `warning-ink-strong` | `warning-surface-strong` | 4.93 |
| `danger-ink` | `danger-surface` | 6.17 |
| `danger-ink` | `danger-surface-strong` | 5.51 |
| `info-ink` | `info-surface` | 5.17 |
| `surface` | `ink` | 13.72 |
| `surface` | `ink-hover` | 10.11 |

## Escala de texto

O nome diz o papel; tamanho, entrelinha, espaçamento e peso vêm juntos, porque é assim que
a escolha é feita — ninguém decide `2.25rem`, decide "título de página".

| Token | Tamanho | Entrelinha | Espaçamento | Peso | Uso |
| --- | --- | --- | --- | --- | --- |
| `text-display` | 2.25rem | 1.1 | -0.04em | 600 | título da página |
| `text-display-lg` | 3rem | 1.05 | -0.04em | 600 | o mesmo título a partir de `sm` |
| `text-metric-lg` | 2.25rem | 1.1 | -0.03em | 600 | score no detalhe da oportunidade |
| `text-metric` | 1.875rem | 1.15 | -0.03em | 600 | número do tile da Visão geral |
| `text-metric-sm` | 1.5rem | 1.2 | -0.03em | 600 | score no cartão da Inbox |
| `text-section` | 1.125rem | 1.4 | — | 600 | título de seção |
| `text-overline` | 0.75rem | 1.3 | 0.08em | 600 | cabeçalho de tabela |
| `text-body` | 1rem | 1.75 | — | — | texto corrido |
| `text-prose` | 0.875rem | 1.5 | — | — | resumo dentro de cartão |

`text-sm` e `text-xs` continuam vindo da escala do Tailwind: são rótulo, célula e legenda,
já eram uma escala declarada, e trocá-los por apelidos nossos moveria cem chamadas sem
mudar uma decisão.

## Forma e ritmo

| Token | Valor | Uso |
| --- | --- | --- |
| `rounded-shell` | 2rem | raio do invólucro da página |
| `shadow-shell` | `0 24px 70px rgb(23 50 45 / 0.10)` | a única elevação da interface |
| `mt-section`, `gap-section` | 2.5rem | distância entre seções de uma tela |
| `mt-block`, `gap-block` | 1.5rem | distância entre blocos dentro de uma seção |

A sombra é o único lugar onde a cor aparece fora da paleta, e por isso é um token: era um
`rgba` cru dentro de uma classe, invisível para a regra de lint que só olhava hexadecimal.

## Ajuste registrado

Um par reprovou e foi corrigido:

```text
muted  #6d827b → #61746e
```

O valor antigo dava 4.09 sobre `surface` e 3.72 sobre `canvas`, abaixo de AA para texto
normal — e era a cor mais usada da interface, em rótulo, dica e metadado. O novo mantém
matiz e saturação e apenas escurece o suficiente para passar nos dois fundos. Nenhuma outra
cor mudou.

## Como isso é mantido

`eslint.config.js` recusa literal hexadecimal em `.ts` e `.tsx` com
`no-restricted-syntax`. A regra roda em `npm run check`, que o CI executa: uma cor nova
precisa virar token antes de entrar numa tela.
