# DESIGN.md — Opportunity Radar (interface web)

Fonte de verdade de tokens e regras visuais de `apps/web`. Origem: SPEC
[46 — Redesenho da interface](docs/46-spec-redesign-ui.md) (§4.1 a §4.3, decisões D1 a D15).
Os tokens vivem em `apps/web/src/styles.css` (`@theme`); a medição de contraste está em
[docs/35-design-tokens.md](docs/35-design-tokens.md) e é imposta por
`apps/web/src/styles.test.ts`. Se este arquivo e o CSS divergirem, o CSS é o valor, este
arquivo é a regra: corrija o que estiver errado no mesmo commit.

**Referência visual:** captura de tela "Audit log" fornecida pelo usuário
([captura "Audit log"](docs/assets/audit-log-reference.png)). Os traços abaixo (§4.1 da SPEC)
são a descrição normativa.

## 1. Traços a reproduzir

- Fundo de aplicação cinza neutro; conteúdo em painel branco de raio ~16px, borda fina, sem
  sombra.
- Sidebar de ~240px: rótulos de grupo pequenos e cinzas, itens ícone + rótulo, item ativo
  como pílula branca com texto escuro (D4: sem faixa de abas do navegador, D15).
- Cabeçalho de página: título ~20px/600 + subtítulo cinza + ação secundária outlined à
  direita (D6: o botão primário escuro segue para ação de formulário).
- Filtros como pílulas outlined (`<select>` nativo estilizado, D3), busca à direita.
- Tabela densa: linha mínima de 44px, cabeçalho cinza claro sem caixa alta, divisórias de
  1px, texto primário escuro + secundário cinza, chips outlined, rodapé de paginação.
- Inter em tamanhos pequenos (13-14px corpo). Um só acento, só em estado de UI.

## 2. Cor (somente tema claro)

| Token | Valor | Papel |
| --- | --- | --- |
| `canvas` | `#f4f4f5` | fundo do app e da sidebar |
| `surface` | `#ffffff` | painel, linha, campo, pílula, item ativo da sidebar |
| `raised` | `#ffffff` | compatibilidade; igual a `surface` |
| `panel` | `#fafafa` | cabeçalho de tabela, bloco de resumo |
| `line` | `#e4e4e7` | borda do painel, divisória de linha |
| `line-strong` | `#d4d4d8` | borda de pílula/botão outlined, chip |
| `control-line` | `#8a8a8a` | borda de campo de texto e checkbox (3.45:1, WCAG 1.4.11) |
| `ink` | `#171717` | texto primário, botão primário |
| `ink-hover` | `#404040` | botão primário em hover |
| `subtle` | `#525252` | subtítulo, texto secundário |
| `muted` | `#6b6b6b` | rótulo de grupo, metadado, hora |
| `accent` | `#c2410c` | página atual, marca de ativo (D5, D14) |
| `accent-ink` | `#c2410c` | texto/borda de página atual; único uso do laranja como texto |
| `accent-surface` | `#fff1ea` | hover da página atual, aviso leve |
| `brand` | `#d7f06f` | logotipo (D13): mantém o lima original, nunca o acento |

Tons semânticos (sucesso, atenção, erro, informação) mantêm a estrutura
superfície/traço/texto, com matiz neutro reajustado; valores e contrastes em
`docs/35-design-tokens.md`. Nome pelo papel, não pelo tom: um tema escuro futuro (fora de
escopo, SPEC §2) troca valores sem tocar telas.

## 3. Forma, tipografia e ritmo

| Token | Valor | Uso |
| --- | --- | --- |
| `radius-panel` | 1rem | painel de conteúdo |
| `radius-control` | 0.5rem | pílula, botão, campo, item ativo da sidebar |
| `radius-chip` | 0.375rem | chips e badges outlined |
| sombra | nenhuma | elevação só por borda; menu aberto pode ter `0 4px 12px rgb(0 0 0 / .06)` |
| `font-sans` | Inter variável auto-hospedada + `system-ui` | ver §5 |
| `text-page-title` | 1.25rem / 1.75rem / 600 | título de página |
| `text-body-sm` | 0.875rem / 1.25rem / 400 | célula, corpo, subtítulo |
| `text-caption` | 0.75rem / 1rem / 500 | grupo da sidebar, chip, "Exibindo…" |
| altura de controle | 2rem (`sm`), 2.25rem (padrão); 44px abaixo de `md` | alvo de toque |
| linha de tabela | 2.75rem mínimo | densidade |
| sidebar | 15rem, `p-3`, item `h-9` | largura fixa `md+` |

Os tokens de transição (`text-display*`, `rounded-shell`, `shadow-shell`, `mt-section`, `mt-block`)
foram removidos em F46-09, com a última tela migrada.

## 4. Regras

1. Nenhum hexadecimal literal em `.ts/.tsx` (lint `no-restricted-syntax`); valor novo vira
   token em `styles.css`.
2. Texto: contraste >= 4.5:1 em todo par documentado. Componente de interface (campo,
   checkbox): >= 3:1. Orange como texto só via `accent-ink`. Falha em
   `apps/web/src/styles.test.ts`.
3. Acento laranja: página atual, ativo/hover de link, contador de atenção. Nunca fundo
   grande nem texto pequeno sobre cinza; nunca identidade (o logotipo usa `brand`).
4. Foco: anel `:focus-visible` de 3px em `ink`, offset 3px; invertido sobre fundo escuro.
5. Estado nunca só por cor: texto no chip, `aria-current` no item ativo, borda e peso na
   página atual.
6. Sem animação nova; transições respeitam `prefers-reduced-motion`.
7. Sem biblioteca de componentes de terceiros (D3). Textos em português.
8. Migração por valores, não por nomes (D2): `canvas`, `surface`, `ink`, `muted`, `line`,
   `accent` e tons semânticos mantêm o nome.

## 5. Fonte (R3)

Inter variável, subset latin, `font-display: swap`, auto-hospedada pelo pacote npm
`@fontsource-variable/inter` (arquivo `inter-latin-wght-normal.woff2`, ~47 KB, referenciado
por `@font-face` em `styles.css` e empacotado pelo Vite). Fallback: `system-ui`. Não há
requisição a terceiro em tempo de execução. Medição de LCP/CLS fica para F46-10.
