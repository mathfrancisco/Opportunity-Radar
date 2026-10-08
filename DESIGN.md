# DESIGN.md — Opportunity Radar (interface web)

Fonte de verdade de tokens e regras visuais de `apps/web`. Origem: SPEC
[54 — Redesenho completo do frontend](docs/54-spec-redesign-completo-frontend.md) (§5),
direção visual aceita em 2026-10-07; referência: protótipo estático e capturas em
[docs/54-review/](docs/54-review/). A [SPEC 46](docs/46-spec-redesign-ui.md) é só a base
anterior. Os tokens vivem em `apps/web/src/styles.css` (`@theme`); a medição de contraste
está em [docs/35-design-tokens.md](docs/35-design-tokens.md) e é imposta por
`apps/web/src/styles.test.ts`. Se este arquivo e o CSS divergirem, o CSS é o valor, este
arquivo é a regra: corrija o que estiver errado no mesmo commit.

## 1. Traços a reproduzir

- Espaço de trabalho de decisão de carreira: claro, sóbrio, em petróleo, slate e tinta.
  Não é um painel administrativo genérico.
- Fundo `canvas` quase branco; sidebar de ~15rem em tom próprio (`sidebar`) com borda
  estrutural à direita; conteúdo direto sobre o `canvas`, painéis em `surface`.
- Sidebar em três grupos pela pergunta que respondem: **Decidir** (Visão geral, Inbox,
  Pipeline), **Pesquisar** (Empresas), **Operar** (Fontes, Homologação, Perfil, Status).
  Item atual: fundo `surface`, texto `ink` semibold e marcador petróleo na borda esquerda.
- Logotipo: marca petróleo com glifo `surface`.
- Cabeçalho de página: título 24px/600 com espaçamento apertado, subtítulo `subtle`, no
  máximo uma ação à direita. Ação primária em petróleo.
- Tabela e lista densas: cabeçalho `panel`, divisória `divider`, alvos de 44px abaixo de `md`.
- Prazo e próxima ação usam `warning-ink`; nunca a cor da marca.
- Sem gradiente e sem sombra difusa. Inter em tamanhos pequenos.

## 2. Cor (somente tema claro)

| Token | Valor | Papel |
| --- | --- | --- |
| `canvas` | `#f7f8f8` | fundo do app |
| `surface` | `#ffffff` | painel, linha, campo, item atual da sidebar, texto sobre petróleo |
| `raised` | `#ffffff` | compatibilidade; igual a `surface` |
| `panel` | `#f1f5f5` | cabeçalho de tabela, bloco de resumo |
| `sidebar` | `#eef3f3` | fundo da sidebar e da barra do menu móvel |
| `line` | `#cbd7d8` | borda estrutural silenciosa de painel |
| `line-strong` | `#9fb2b4` | borda de botão outlined, pílula, chip e divisão da sidebar |
| `divider` | `#dde7e7` | separador de linha de tabela e lista |
| `control-line` | `#71878a` | borda de campo de texto e checkbox (3.79:1, WCAG 1.4.11) |
| `ink` | `#132229` | texto primário |
| `ink-hover` | `#2a3b42` | `ink` em hover, quando usado como fundo |
| `subtle` | `#405159` | subtítulo, texto secundário, item de navegação |
| `muted` | `#52626a` | rótulo de grupo, metadado, hora |
| `neutral-ink` | `#405159` | texto de badge neutro |
| `accent` | `#0b5d66` | ação primária, foco, marcador do item atual, sublinhado de link |
| `accent-hover` | `#084b52` | ação primária em hover |
| `accent-ink` | `#0b5d66` | texto de link e de item atual |
| `accent-surface` | `#edf5f4` | seleção, contexto, hover leve |
| `brand` | `#0b5d66` | fundo do logotipo; glifo em `surface` |

Tons semânticos (valores e contrastes em `docs/35-design-tokens.md`):

| Estado | Superfície | Traço | Texto |
| --- | --- | --- | --- |
| Sucesso | `success-surface` `#e3f1ed`, `-soft` `#eef7f4`, `-strong` `#d3e9e1` | `success-line` `#8fbfae` | `success-ink` `#14553c`, `-strong` `#0f4a33` |
| Atenção | `warning-surface` `#fdf3e9`, `-strong` `#f5eadc` | `warning-line` `#e9c89d` | `warning-ink` `#704015`, `-strong` `#854312` |
| Erro | `danger-surface` `#fbeeee`, `-strong` `#f7e4e4` | `danger-line` `#e2b8b8` | `danger-ink` `#8c3030` |
| Informação | `info-surface` `#edf5f4` | — | `info-ink` `#314a4d` |

Nome pelo papel, não pelo tom: um tema escuro futuro (fora de escopo) troca valores sem
tocar telas.

## 3. Forma, tipografia e ritmo

| Token | Valor | Uso |
| --- | --- | --- |
| `radius-panel` | 0.5rem | painel, tabela, cartão |
| `radius-control` | 0.375rem | botão, campo, pílula, item da sidebar |
| `radius-chip` | 0.25rem | chips e badges outlined |
| `shadow-overlay` | `0 4px 12px rgb(19 34 41 / 0.12)` | única sombra: gaveta e menu sobrepostos |
| `font-sans` | Inter variável auto-hospedada + `system-ui` | ver §5 |
| `text-page-title` | 1.5rem / 2rem / 600 / -0.02em | título de página |
| `text-section` | 1.125rem / 1.4 / 600 | título de seção |
| `text-body` | 1rem / 1.75 | texto corrido |
| `text-body-sm`, `text-prose` | 0.875rem | célula, corpo, subtítulo |
| `text-caption` | 0.75rem / 1rem / 500 | grupo da sidebar, chip, metadado |
| `text-metric-lg`, `-metric`, `-metric-sm` | 2.25 / 1.875 / 1.5rem / 600 | números de métrica, com algarismos tabulares |
| altura de controle | 2rem (`sm`), 2.25rem (padrão); 44px abaixo de `md` | alvo de toque |
| espaçamento | base de 4px; 16-24px em decisão, 8-12px em lista densa | ritmo |
| sidebar | 15rem, `p-3`, item `h-9` | largura fixa `md+` |

## 4. Regras

1. Nenhum hexadecimal literal em `.ts/.tsx` (lint `no-restricted-syntax`); valor novo vira
   token em `styles.css`.
2. Contraste medido: texto >= 4.5:1 em todo par documentado; componente de interface (campo,
   checkbox, anel de foco) >= 3:1. Falha em `apps/web/src/styles.test.ts`.
3. Um só acento: petróleo. Serve a orientação, item atual, links, foco e ação primária.
   Cores de estado continuam semânticas (sucesso, atenção, erro, informação) e nunca viram
   marca nem decoração.
4. Foco: anel `:focus-visible` de 3px em `accent` (petróleo), offset 3px, desenhado fora do
   elemento; o afastamento o mantém visível ao redor de um botão petróleo.
5. Estado nunca só por cor: texto no chip, `aria-current` e marcador mais peso no item atual.
6. Sem animação nova; `prefers-reduced-motion: reduce` neutraliza animação e transição
   globalmente.
7. A única primitiva de acessibilidade aprovada é `@radix-ui/react-dialog@1.2.0`,
   somente atrás de wrappers em `apps/web/src/components/ui/`; rotas, formulários e
   módulos de feature nunca a importam diretamente. Não adicionar outro primitive Radix
   sem nova medição; textos da interface permanecem em português.
8. Migração por valores, não por nomes: `canvas`, `surface`, `ink`, `muted`, `line`,
   `accent` e tons semânticos mantêm o nome; token novo só quando o papel não tem nome.
9. Somente tema claro; modo escuro está fora de escopo.

## 5. Fonte (R3)

Inter variável, subset latin, `font-display: swap`, auto-hospedada pelo pacote npm
`@fontsource-variable/inter` (arquivo `inter-latin-wght-normal.woff2`, ~47 KB, referenciado
por `@font-face` em `styles.css` e empacotado pelo Vite). Fallback: `system-ui`. Não há
requisição a terceiro em tempo de execução.
