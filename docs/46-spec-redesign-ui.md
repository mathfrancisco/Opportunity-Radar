# SPEC — Redesenho da interface web (visual "admin" claro: sidebar, painel branco, tabelas densas)

- **Status:** Planejada; nenhuma capacidade abaixo é declarada entregue
- **Data:** 2026-09-29
- **Escopo:** mudar a aparência e a estrutura de layout de `apps/web` para o padrão da
  imagem de referência (fundo cinza neutro, painel branco arredondado, sidebar agrupada,
  cabeçalho de página com ação secundária, linha de filtros em pílulas, tabela densa com
  rodapé de paginação), sem alterar API, regras de domínio, rotas nem textos de negócio.
- **Referência visual:** captura de tela fornecida pelo usuário (`Captura de tela
  2026-09-29 153732.png`, tela "Audit log"). A imagem não está versionada; o primeiro
  card (F46-01) a copia para `docs/assets/` como parte do `DESIGN.md`.
- **Cards de execução:** ainda não criados; as fatias estão em §8 e viram cards `F46-xx`
  quando esta SPEC for aceita.
- **Documentos relacionados:** [Tokens de design (35)](35-design-tokens.md),
  [Roadmap de interface (34)](34-roadmap-interface.md), Fase 15 (cards F15-01 a F15-09,
  tokens, componentes, acessibilidade, responsividade),
  [SPEC de descoberta de startups (45)](45-spec-descoberta-startups.md) (o selo "startup"
  da Inbox precisa sobreviver ao redesenho)

---

## 1. Objetivo e limite da promessa

Fazer as telas existentes parecerem e se comportarem como a referência: leve, densa,
neutra, com uma única cor de acento usada com parcimônia. É uma mudança de **apresentação**:

- nenhuma rota nova, nenhum endpoint novo, nenhum campo de dados novo;
- nenhum gate, veredito, score ou regra de elegibilidade muda (mesma invariante da Fase 20);
- todo comportamento hoje coberto por teste continua coberto — o redesenho troca classes e
  estrutura, não contratos.

Não é promessa de pixel-perfect: a referência é um app diferente (loja), com outra
densidade de conteúdo. O critério é aderência aos **traços** de §4.1, verificada por teste
de componente e checagem visual (§11).

## 2. Não-objetivos

- Tema escuro (hoje não existe; a Fase 15 o deixou fora e esta SPEC mantém). Os tokens
  ficam nomeados por papel para não impedir um tema futuro.
- Biblioteca de componentes de terceiros (Radix, shadcn, MUI etc.). Continua Tailwind 4 +
  componentes próprios (decisão D3).
- Novas telas, novos filtros de dados, novos campos, seleção em massa com ações (o
  checkbox da referência só entra onde houver ação em lote real; ver §6).
- Trocar React Router, TanStack Query ou o processo de build.
- Internacionalização. Textos seguem em português.

## 3. Estado atual (verificado no código em 2026-09-29)

**Stack.** React 19, react-router-dom 7, TanStack Query, Tailwind 4 via `@tailwindcss/vite`
(`apps/web/package.json`). Sem CSS modules, sem biblioteca de componentes, sem ícones de
terceiros (`components/icons.tsx` tem SVGs próprios). Fonte declarada `Inter, ui-sans-serif,
system-ui` em `styles.css`, mas **nenhuma fonte é carregada** (sem `@font-face`/link): onde
Inter não está instalada, cai em `system-ui`.

**Estilo.** Tokens em `@theme` de `apps/web/src/styles.css`, documentados em
[`35-design-tokens.md`](35-design-tokens.md), incluindo contraste medido. A paleta atual é
verde-esverdeada (`canvas #f2f5ef`, `ink #17322d`, `accent #d7f06f` lima). O ESLint recusa
literal hexadecimal em `.ts/.tsx` (`no-restricted-syntax`, roda em `npm run check` e no
CI). Não há tema escuro (`dark:`/`prefers-color-scheme` ausentes). Única sombra:
`shadow-shell`. **Não existe `DESIGN.md` na raiz.**

**Layout.** `components/PageShell.tsx` é o único invólucro: `main` com fundo `canvas`, um
cartão central `max-w-5xl` com `rounded-shell` (2rem) e sombra, **navegação horizontal no
topo** agrupada em "Dia a dia / Catálogo / Diagnóstico", título `text-display` (2.25rem a
3rem), *eyebrow* acima do título e descrição abaixo. Há link "Pular para o conteúdo".

**Rotas** (`app/App.tsx`, 10 telas; `*` cai em Visão geral):

| Rota | Tela | Linhas | Forma atual |
| --- | --- | ---: | --- |
| `/` | `OverviewPage` | 737 | tiles de métrica, tabela de métricas por fonte (`DataTable` + `Toolbar` de janela), listas por seção |
| `/inbox` | `InboxPage` | 718 | `SearchBar` + buscas salvas + 5 `<select>` em grade + `Toolbar` "Candidatura" + **lista de cartões** + paginação "Anterior/Próxima" (pageSize fixo 25, `?page=` na URL) |
| `/opportunities/:id` | `OpportunityDetailPage` | 629 | detalhe com blocos, `DataTable`, `AnalysisPanel`, `ApplicationPanel` |
| `/applications` | `PipelinePage` | 180 | colunas por estágio (grade de cartões) |
| `/companies` | `CompaniesPage` | 233 | tabela `md+` (própria, sem `DataTable`) e cartões no mobile; `SearchBar` |
| `/companies/:id` | `CompanyDetailPage` | 424 | detalhe + formulários |
| `/sources` | `SourcesPage` | 355 | `DataTable`, painéis de criação/controle/manual |
| `/sources/homologation-queue` | `HomologationQueuePage` | 37 | fila (`HomologationQueue`, 354) |
| `/profile` | `ProfilePage` | 492 | formulários e versões |
| `/status` | `StatusPage` | 68 | estado de prontidão |

**Componentes compartilhados** (`apps/web/src/components/`): `Button` (primary/secondary,
`rounded-xl`), `Card`, `DataTable` (rola dentro do contêiner, primeira coluna fixa
opcional, cabeçalho em caixa alta `text-overline`), `Toolbar` (grupo de botões
mutuamente exclusivos), `SearchBar` (campo + botão "Buscar"), `Field` (rótulo + controle),
`StatusBadge` (mapas de rótulo/tom recebidos por parâmetro), `states` (carregando/vazio/
erro), `skeletons`, `Unavailable`, `icons`. Quase todos têm teste ao lado.

**Testes.** Vitest + jsdom (`vite.config.ts`), testes de componente e de rota
(`InboxPage.test.tsx`, `OverviewPage.test.tsx`, `SourcesPage.test.tsx`,
`ProfilePage.test.tsx`, `OpportunityDetailPage.test.tsx`); `npm run check` = lint +
typecheck + test + build. Não há teste visual/screenshot em `apps/web`. Existe jornada
Playwright separada em `tests/e2e/browser/` (rodada no CI, `pipeline.yml`, com upload de
screenshots) que usa `getByRole/getByText/getByLabel` — **é o contrato de seletor que o
redesenho não pode quebrar**.

**Distância até a referência** (o que muda de fato):

| Traço da referência | Hoje |
| --- | --- |
| Fundo cinza neutro + painel branco | fundo verde-claro + cartão `raised` creme com sombra grande |
| Sidebar esquerda agrupada | navegação horizontal no topo (mesmos três grupos) |
| Título ~20px + subtítulo cinza | título 36-48px, eyebrow, descrição 16px |
| Ação secundária outlined no canto do título | botões no corpo; primário escuro `bg-ink` |
| Filtros em pílulas outlined com ícone | 5 `<select>` nativos em grade + `Toolbar` de botões |
| Tabela densa com divisórias finas | Inbox em cartões; Companies com tabela própria; demais com `DataTable` de cabeçalho em caixa alta |
| Rodapé "Viewing 1 to 15 of N" + páginas numeradas + itens por página | "Página X de Y" + Anterior/Próxima; sem itens por página |
| Acento laranja-avermelhado, raro | acento lima usado em sublinhado de link e anel de foco |
| Sombras quase ausentes, bordas sutis | uma sombra grande, raios 2xl/xl/full |

## 4. Design alvo

### 4.1 Traços a reproduzir

Fundo de aplicação cinza neutro; conteúdo em painel branco de raio médio (~16px) com borda
fina e sem sombra; sidebar de ~240px com rótulos de grupo pequenos e cinzas, itens
"ícone + rótulo", separadores finos, item ativo como pílula branca com texto escuro;
cabeçalho de página com título (~20px, 600) + subtítulo cinza e ação outlined à direita;
linha de filtros com pílulas outlined (ícone + rótulo + chevron) e busca à direita; tabela
densa (linhas ~44px, cabeçalho cinza claro em caixa normal, divisórias 1px, texto primário
em negrito/escuro + secundário cinza na mesma célula, *chips* outlined pequenos, avatar +
nome, data escura + hora cinza); rodapé de tabela; tipografia Inter em tamanhos pequenos
(13-14px corpo); um só acento, só em página atual, foco e marcas de estado ativo.

### 4.2 Decisões

- **D1 — `DESIGN.md` na raiz.** Não existe hoje. A regra do projeto é seguir `DESIGN.md`
  quando houver; portanto a **primeira fatia cria `DESIGN.md`** (via skill `design-md`,
  com a referência como fonte) e passa a ser a fonte de verdade de tokens e regras.
  `docs/35-design-tokens.md` é atualizado no mesmo card para apontar para ele (sem duas
  fontes divergentes).
- **D2 — Migração por tokens, não por reescrita.** Os **nomes** dos tokens atuais
  (`canvas`, `surface`, `ink`, `muted`, `line`, `accent`, tons semânticos) são mantidos;
  mudam os **valores** e entram poucos tokens novos. Assim as ~9k linhas de rota mudam
  pouco na primeira passada e o lint de hexadecimal continua valendo.
- **D3 — Sem biblioteca de componentes.** Dropdown-pílula, paginação e sidebar são
  pequenos e já há disciplina de acessibilidade própria. O dropdown-pílula é um
  `<select>` nativo estilizado (§7), o que preserva teclado, leitor de tela e `getByLabel`
  nos testes existentes.
- **D4 — Faixa de abas do navegador: fora de escopo (recomendação).** Na referência é
  cromo do sistema/navegador (semáforo, voltar/avançar, abas "Order #…"), não UI do app.
  Reproduzi-la duplicaria o navegador e exigiria estado de abas sem caso de uso no radar.
  Também não se aplica o "Back to app" do topo da sidebar (o radar é um app só): o topo da
  sidebar leva o logotipo/nome. Um link "voltar" existe só nos detalhes (§6).
- **D5 — Acento laranja-avermelhado** substitui o lima. Uso restrito a: página atual na
  paginação, marca de item ativo/hover de link e contadores de atenção. Nunca em fundo
  grande nem em texto pequeno sobre cinza.
- **D6 — Botão primário continua existindo** (escuro, `ink`) para a ação principal de
  formulário (salvar, criar); a ação de cabeçalho de página usa o secundário outlined, como
  na referência. Não se troca semântica de botão.
- **D7 — Mobile.** Sidebar vira gaveta (menu) abaixo de `md`; o layout de cartões atual da
  Inbox/Companies é mantido como visão `< md` da mesma tabela (padrão que `CompaniesPage`
  já usa).

### 4.3 Tokens (valores propostos; contraste medido em 2026-09-29, alvo AA)

Somente tema claro. As razões WCAG 2.x abaixo foram calculadas sobre os valores
propostos; o card F46-01 repete a medição contra o CSS real e atualiza
`35-design-tokens.md`.

**Superfícies e traços**

| Token | Valor proposto | Substitui | Uso |
| --- | --- | --- | --- |
| `canvas` | `#f4f4f5` | `#f2f5ef` | fundo do app e da sidebar |
| `surface` | `#ffffff` | igual | painel de conteúdo, linha, campo, pílula, item ativo da sidebar |
| `raised` | `#ffffff` | `#fbfcf8` | mantido por compatibilidade; igual a `surface` |
| `panel` | `#fafafa` | `#f7faf6` | cabeçalho de tabela, bloco de resumo |
| `line` | `#e4e4e7` | `#dce4dc` | borda do painel, divisórias de linha |
| `line-strong` | `#d4d4d8` | `#c8d4c8` | borda de pílula/botão outlined, chips |
| `control-line` | `#8a8a8a` (**novo**) | — | borda de campo de texto e checkbox (3.45:1 sobre `surface`, atende os 3:1 de WCAG 1.4.11); ver R4 |
| `accent` | `#c2410c` | `#d7f06f` | página atual, marca de ativo |
| `accent-surface` | `#fff1ea` (**novo**) | — | hover da página atual, aviso leve |

**Texto**

| Token | Valor | Contraste | Uso |
| --- | --- | --- | --- |
| `ink` | `#171717` | 17.93 sobre `surface`, 16.31 sobre `canvas` | texto primário, botão primário |
| `ink-hover` | `#404040` | não medido (fundo do botão) | botão primário em hover |
| `subtle` | `#525252` | 7.81 / 7.11 | subtítulo, texto secundário de peso |
| `muted` | `#6b6b6b` | 5.33 sobre `surface`, 4.85 sobre `canvas` | rótulo de grupo, metadado, hora, "Exibindo…" |
| `accent-ink` | `#c2410c` | 5.18 sobre `surface`, 4.71 sobre `canvas` | texto/borda de página atual |

**Tons semânticos** (sucesso, atenção, erro, informação): mantêm a estrutura
superfície/traço/texto de `35-design-tokens.md`, com matiz reajustado para neutro sem mexer
nas razões já medidas (≥ 4.5). Os valores não são redefinidos aqui um a um: o F46-01 troca o
matiz e reexecuta a tabela de contraste; qualquer par que reprovar é escurecido, como já foi
feito com `muted`.

**Forma, tipografia e ritmo**

| Token | Valor | Uso |
| --- | --- | --- |
| `radius-panel` | `1rem` (16px) | painel de conteúdo (substitui `rounded-shell` 2rem) |
| `radius-control` | `0.5rem` (8px) | pílulas de filtro, botões, campos, item ativo da sidebar |
| `radius-chip` | `0.375rem` (6px) | chips/badges outlined |
| `radius-full` | 9999px | avatar |
| sombra | nenhuma | remover `shadow-shell`; elevação só por borda (menu aberto pode ter sombra leve própria, `0 4px 12px rgb(0 0 0 / .06)`) |
| `font-sans` | Inter (auto-hospedada, pesos 400/500/600) + fallback `system-ui` | ver R3 |
| `text-page-title` | 1.25rem / 1.75rem / 600 / -0.01em | título de página (substitui `text-display*` nas telas migradas) |
| `text-body-sm` | 0.875rem / 1.25rem / 400 | célula, corpo, subtítulo |
| `text-caption` | 0.75rem / 1rem / 500 | rótulo de grupo da sidebar, chip, "Exibindo…" |
| `text-metric*` | mantidos | tiles da Visão geral |
| altura de controle | 2rem (32px) pílula/botão `sm`; 2.25rem (36px) botão padrão | alvo de toque em §9 |
| altura de linha de tabela | 2.75rem (44px) mínimo | densidade da referência |
| sidebar | 15rem, `p-3`, item `h-9`, gap `0.25rem` | largura fixa `md+` |
| espaçamento de página | painel `p-6`; título→filtros `mt-5`; filtros→tabela `mt-4` | substitui `mt-section/block` nas telas migradas |

`text-display`, `text-display-lg`, `rounded-shell`, `shadow-shell` e `mt-section`
permanecem definidos até a última tela migrar (F46-09); a remoção é o último passo, com o
lint de tokens garantindo que nada os use.

## 5. Componentes alvo

Todos em `apps/web/src/components/`, cada um com teste ao lado.

| Componente | Novo/Muda | Contrato |
| --- | --- | --- |
| `AppShell` | substitui o miolo de `PageShell` | sidebar + painel; **mantém a API de `PageShell`** (`current`, `title`, `description`, `children`, `footer`) para não tocar as 10 rotas; `eyebrow` passa a opcional e sem destaque visual (D10) |
| `Sidebar` | novo | grupos "Dia a dia / Catálogo / Diagnóstico" (mesmos itens de hoje), rótulo `text-caption` cinza, itens ícone+rótulo, ativo = pílula `surface` com `aria-current="page"`, `<nav aria-label="Navegação principal">`, gaveta `< md` |
| `PageHeader` | novo | `<h1>` + subtítulo + slot `actions` (Button secundário à direita) |
| `Button` | ajusta | variantes `primary` e `secondary` (outlined, borda `line-strong`, raio `radius-control`), tamanho `sm` 32px; anel de foco (§9) |
| `FilterPill` | novo | `<label>` visível + `<select>` nativo estilizado (ícone à esquerda, chevron à direita, borda `line-strong`); estado "ativo" (borda `ink`) quando valor ≠ padrão |
| `SearchInput` | substitui `SearchBar` | campo com ícone de lupa, ~20rem, à direita da linha de filtros; mantém `role="search"`, rótulo, envio por Enter; botão "Buscar" fica `sr-only` (D11) |
| `FilterBar` | novo | flex com quebra; pílulas à esquerda, `SearchInput` à direita |
| `DataTable` | reescreve o visual | cabeçalho `panel`, `text-caption` `muted` **sem caixa alta**, linha mín. 44px, divisória `line`, contêiner com borda `line` + `radius-control`, rola dentro do contêiner, primeira coluna fixa opcional (já existe); coluna de seleção (checkbox) só com `selectable` |
| Células | novos, finos | `PrimaryText`+`SecondaryText` (negrito escuro + cinza), `DateTimeCell` (data `ink`, hora `muted`), `Chip` (outlined, `radius-chip`), `Avatar` (iniciais; sem imagem) |
| `StatusBadge` | ajusta | vira `Chip` outlined com ponto de cor opcional; mapas de rótulo/tom recebidos continuam iguais (API preservada) |
| `Pagination` | novo | "Exibindo X a Y de N", botões numerados com elipse, atual `border-accent text-accent-ink` + `aria-current="page"`, prev/next com `aria-label`, `<nav aria-label>`; `PageSizeSelect` ("Itens por página") |
| `Toolbar` | mantido | continua para janelas de tempo curtas (Visão geral); ganha visual de pílula; não vira dropdown |
| `Card` | ajusta | borda `line`, `radius-control`, sem sombra |
| `states`/`skeletons` | ajusta cores | sem mudança de estrutura; skeleton de tabela com a altura de linha nova (evita salto, F15-09) |

Rótulos visíveis em português ("Exibindo 1 a 15 de 145 oportunidades", "Itens por
página"), não os textos em inglês da referência.

## 6. Mapeamento por tela

| Tela | Padrão de referência | Mudanças |
| --- | --- | --- |
| **Oportunidades (Inbox)** | tabela + filtros + paginação | Cartões viram linhas (`DataTable`): coluna "Oportunidade" (título em negrito com link + "empresa · local" cinza, chips "Possível duplicata"/"Startup · YC S24" ao lado), "Decisão" (`VerdictBadge` como chip), demais campos hoje presentes no cartão, e a ação por linha. Os 5 `<select>` viram `FilterPill` na `FilterBar`; a busca vira `SearchInput` à direita; o `Toolbar` "Candidatura" vira `FilterPill`; `SavedSearches`/`SaveSearchForm` vão para um dropdown "Buscas salvas" à direita da `FilterBar` (D12). Paginação vira `Pagination` (URL `?page=` preservada; `PageSizeSelect` só se a API aceitar tamanho variável, D8). Marcar "Não é para mim" continua por linha (botões secundários `sm`). `< md`: cartão atual. |
| **Visão geral** | painel + tabela | Tiles de métrica com borda `line`, sem sombra; "Métricas operacionais por fonte" segue `DataTable` com novo visual e `Toolbar` de janela como pílula à direita do título da seção. Listas tabulares de "Decisão de hoje" viram tabela compacta. Sem paginação. |
| **Fontes** | tabela | `DataTable` novo; nome da fonte em negrito + tipo em cinza; estado (`StatusBadge`) como chip; "Adicionar fonte" vai para `PageHeader.actions` (secundário outlined); "Executar agora" botão secundário `sm` por linha. Painéis de criação/controle/manual mantidos, com `Card` novo. Sem filtros novos. |
| **Fila de homologação** | tabela | `HomologationQueue` reutiliza `DataTable`/`Chip`; ações por linha como botões `sm`. |
| **Empresas** | tabela + busca | Tabela própria migra para `DataTable`; `SearchBar`→`SearchInput`; prioridade/status/verificação como chips; "Fontes" em cinza. Paginação só se a lista já for paginada (D8). |
| **Detalhe da oportunidade** | detalhe | Sem tabela principal: blocos em `Card` novo dentro do painel; `PageHeader` com título + ações à direita; link "voltar" no topo do painel (papel do "Back to app"); `DataTable` internas com o novo visual; `AnalysisPanel`/`ApplicationPanel` só recebem tokens. |
| **Detalhe da empresa** | detalhe | idem; formulários com `Field` e controles `radius-control`/`control-line`. |
| **Candidaturas** | colunas por estágio | Mantém colunas, cartões com borda `line`; sem tabela. Alternativa de tabela por estágio fora de escopo. |
| **Perfil** | formulário | Só tokens/`Field`/`Button`. |
| **Status** | painel de prontidão | Só tokens; `.status` vira chip mantendo `role`/texto usados nos testes. |

Sem equivalente no radar, portanto não forçado: checkbox de seleção (sem ação em lote hoje;
`selectable` fica opt-in e nenhuma tela o liga nesta SPEC), coluna de avatar/autor (não há
usuário autor; `Avatar` existe para uso futuro), "Exportar CSV" (não existe endpoint; a
ação de cabeçalho da referência é só o *slot* `actions`).

## 7. Detalhes de interação

1. **Ação de cabeçalho.** No máximo um botão secundário por tela; ações de escrita ou
   destrutivas seguem com a confirmação do fluxo atual.
2. **Sidebar.** Ordem e agrupamento iguais aos de hoje; ativo por `aria-current`, nunca só
   por cor. Estado recolhido: fora de escopo.
3. **`FilterPill` é `<select>` nativo.** Vantagem: teclado, leitor de tela, lista nativa no
   mobile e compatibilidade com os testes (`getByLabel`, `selectOptions`). Custo: o menu
   aberto não é estilizável. Aceito; menu customizado só se o custo aparecer em uso (R2).
4. **Filtros na URL.** Continuam nos parâmetros de busca (`?verdict=…&page=…`); mudar
   filtro zera `page` (comportamento atual preservado).
5. **Paginação.** `Pagination` recebe `page`, `pageSize`, `total`; janela com elipse
   (`1 … 4 5 6 … 12`); sem navegação otimista.

## 8. Plano em fatias (cards F46-xx)

Cada fatia é pequena, integra-se sozinha e deixa `npm run check` verde. F46-01 destrava
tudo; 02–06 são independentes entre si depois dele; 07–09 dependem dos componentes.

| Card | Fatia | Entrega | Depende de |
| --- | --- | --- | --- |
| **F46-01** | `DESIGN.md` + tokens | Cria `DESIGN.md` (skill `design-md`), copia a referência para `docs/assets/`, troca **valores** dos tokens (§4.3), adiciona `control-line`, `accent-surface`, `radius-*`, `text-page-title`, auto-hospeda Inter; remove a sombra do shell; reexecuta a tabela de contraste e atualiza `35-design-tokens.md`. Telas mudam de cor, não de estrutura. | — |
| **F46-02** | Shell + sidebar | `AppShell`/`Sidebar`/`PageHeader` com a API de `PageShell` preservada; gaveta `< md`; pular-para-conteúdo mantido; logotipo ajustado (R8); *eyebrow* removido do visual (D10). | 01 |
| **F46-03** | `Button`, `Chip`, `StatusBadge`, `Card` | Novo visual de botão (outlined), chips outlined, cartão sem sombra. | 01 |
| **F46-04** | `DataTable` + células | Novo visual, `PrimaryText/SecondaryText/DateTimeCell`, `selectable` opt-in, skeleton com altura nova. | 01, 03 |
| **F46-05** | `FilterPill`, `SearchInput`, `FilterBar` | Componentes + testes; ainda sem uso nas telas. `SearchInput` com botão "Buscar" em `sr-only` e busca por Enter (D11); dropdown "Buscas salvas" ainda sem UI definida, integrado em F46-07 (D12). | 01, 03 |
| **F46-06** | `Pagination` + `PageSizeSelect` | Componente + testes de janela, elipse e limites. Verifica se a API da Inbox aceita `page_size` variável; se sim, `PageSizeSelect` é integrado; se não, o seletor fica de fora. `CompaniesPage` também é verificada: se paginada, recebe `Pagination` nova; se não, continua sem (D8). | 01, 03 |
| **F46-07** | Migração: Oportunidades | Cartões→linhas, filtros→`FilterBar`, paginação nova; `< md` mantém cartão. "Buscas salvas"/"Salvar busca" movidas para dropdown à direita da `FilterBar` (D12). Fatiar em 07a (tabela) e 07b (filtros+paginação) se o diff passar de ~300 linhas. | 02, 04, 05, 06 |
| **F46-08** | Migração: Fontes, Empresas, Fila | `DataTable` unificado (Empresas deixa a tabela própria); `SearchInput` em Empresas. | 02, 04, 05 |
| **F46-09** | Migração: Visão geral, detalhes, Candidaturas, Perfil, Status | Só tokens/componentes novos; remove `text-display*`, `rounded-shell`, `shadow-shell`, `mt-section` quando sem uso. | 02–08 |
| **F46-10** | Verificação visual e E2E | Screenshots por tela (Playwright existente), ajuste de seletores só se um papel/rótulo mudou de propósito; revisão de contraste e foco; fecha a SPEC. | 01–09 |

Cada card, ao ser criado, segue o formato de `docs/34-roadmap-interface/fase-15/`
(Resultado, Contexto, Escopo, Fora de escopo, Critérios de aceite, Verificação).

## 9. Acessibilidade (WCAG 2.1 AA)

- **Contraste de texto ≥ 4.5:1** em todo par (tabela de §4.3 e a de
  `35-design-tokens.md`, refeita no F46-01). `muted` sobre `canvas` (4.85) é o par mais
  justo; texto de 12px em `muted` só sobre `surface`/`canvas`, nunca sobre `accent-surface`
  sem nova medição. O laranja como **texto** só via `accent-ink` (≥ 4.5 sobre `surface`);
  como borda/ícone, ≥ 3:1.
- **Componentes de interface ≥ 3:1** (1.4.11): campo de texto e checkbox usam
  `control-line`; a pílula, por ter rótulo+ícone+chevron visíveis, pode usar `line-strong`
  (decisão explícita e revisável, R4).
- **Foco.** Mantém o `:focus-visible` global com anel de 3px em `ink` e offset 3px (regra
  atual, escolhida por contraste); sobre fundo escuro (botão primário) o anel inverte para
  `surface`. O laranja não é o anel primário: evita anel colorido sobre chip laranja.
- **Teclado.** Sidebar: `Tab` por link, sem armadilha; a gaveta mobile abre/fecha por botão
  com `aria-expanded`/`aria-controls`, `Esc` fecha e devolve o foco ao botão. Pílulas são
  `<select>` nativos. Paginação: botões reais, página atual `aria-current="page"`, prev/next
  com `aria-label` ("Página anterior", "Próxima página"), desabilitados com `disabled`.
- **Semântica.** Um `<h1>` por página (`PageHeader`); `nav` com `aria-label`; tabela com
  `<th scope="col">` e `caption` `sr-only`; "Exibindo X a Y de N" com `aria-live="polite"`
  ao mudar de página; `role="search"` mantido.
- **Estado nunca só por cor**: chip com texto; item ativo com `aria-current`; página atual
  com borda **e** peso.
- **Alvo de toque.** Controles de 32px são densos como a referência e atendem o mínimo
  24×24 do WCAG 2.2 (2.5.8); em `< md` pílulas, botões e itens da gaveta sobem para 44px.
- **Movimento**: sem animação nova; toda transição respeita `prefers-reduced-motion`.

## 10. Responsividade

- `>= md` (768px): sidebar fixa 15rem + painel; `< md`: barra superior com botão de menu e
  gaveta; painel ocupa a largura toda, sem raio externo e com `p-4`.
- Tabelas rolam **dentro do contêiner** (comportamento atual de `DataTable`, primeira
  coluna fixa opcional); listas primárias (Inbox, Empresas) mantêm visão de cartão `< md`,
  sobre os mesmos dados/componentes de célula.
- `FilterBar` quebra em linhas: `SearchInput` vai para linha própria em largura total
  abaixo de `md`; pílulas quebram, nunca estouram a página.
- Sem rolagem horizontal da página em 320px (`min-width: 320px` do `body` mantido).

## 11. Critérios de aceite e verificação

Cada critério tem teste. Comandos: `cd apps/web && npm run check` por fatia; jornada
Playwright existente (`tests/e2e/browser`) no CI, sem mudança de fluxo.

| Critério | Verificação |
| --- | --- |
| Nenhum hexadecimal literal em `.ts/.tsx`; todo valor novo é token | lint existente (`no-restricted-syntax`) em `npm run check` |
| Cada par texto/fundo documentado ≥ 4.5 (texto) e ≥ 3 (controle) | teste Vitest no F46-01 sobre os valores de `styles.css` falha se algum par reprovar; tabela em `35-design-tokens.md` regenerada |
| `Sidebar` renderiza os 3 grupos e 7 itens de hoje, ativo com `aria-current="page"`; gaveta `< md` abre/fecha com `Esc` e devolve o foco | teste de componente (jsdom) |
| `AppShell` mantém `current`, `title`, `description`, `footer`; "Pular para o conteúdo" continua o primeiro alvo de tabulação | `PageShell.test.tsx` adaptado + teste de ordem de foco |
| `FilterPill` tem rótulo acessível, dispara `onChange`, mostra ativo quando ≠ padrão | teste de componente; `getByLabel` como nos testes de rota |
| `SearchInput` envia por Enter e mantém `role="search"`; botão "Buscar" em `sr-only` (D11) | teste de componente |
| `DataTable`: `th scope=col`, `caption`, linha 44px mín. (classe), `selectable` opt-in com "selecionar todas" rotulado | teste de componente |
| `Pagination`: "Exibindo 1 a 15 de 145", elipse, atual com `aria-current`, prev desabilitado na 1ª e next na última, caso 0 itens | teste de unidade dos limites (0, 1 página, muitas) |
| Inbox: filtros e `?page=` na URL iguais aos de hoje; mudar filtro zera a página; asserções atuais de `InboxPage.test.tsx` seguem verdes (adaptadas só no que mudou de forma: cartão→linha) | testes de rota existentes |
| Selo de startup (`data-testid="startup-badge"`) e "Possível duplicata" continuam na linha | `InboxPage.test.tsx` |
| Jornada E2E passa sem mudar de fluxo; seletores só mudam se um papel/rótulo mudou de propósito, registrado no card | `npx playwright test` em `tests/e2e/browser` (CI) |
| Checagem visual: cada tela migrada tem screenshot em 1280 e 375 anexado ao card e comparado com os traços de §4.1 | screenshots Playwright já enviados como artefato no CI; revisão humana no F46-10 (sem teste de pixel automatizado nesta SPEC, D9) |
| Sem rolagem horizontal da página em 320px | teste Playwright `scrollWidth <= innerWidth` nas telas migradas |

## 12. Riscos

- **R1 — Reescrever demais e quebrar testes/E2E.** Mitigação: API de `PageShell`, de
  `StatusBadge` e nomes de token preservados; migração tela a tela; E2E no CI a cada fatia.
- **R2 — `<select>` nativo não combina com a pílula aberta.** O menu usa o estilo do SO.
  Aceito por acessibilidade e custo (D3); reavaliar se o uso real reclamar.
- **R3 — Fonte Inter.** Hoje só declarada. Auto-hospedar (variável, `font-display: swap`,
  subset latin) evita terceiro e CLS; se o peso pesar, ficar em `system-ui`. Decidir no
  F46-01 com medição de LCP/CLS.
- **R4 — Borda sutil vs. WCAG 1.4.11.** A referência usa bordas de baixo contraste; campos
  e checkbox usam `control-line` (3.45:1) e só a pílula com rótulo usa `line-strong`. Se a
  revisão do F46-10 discordar, escurece-se o `line-strong` da pílula.
- **R5 — Inbox em tabela perde densidade do cartão** (resumo, várias ações). Mitigação:
  decidir no F46-07 quais campos viram coluna, quais viram secundário na célula e quais
  ficam só no detalhe; nada que decide (veredito, duplicata, startup) sai da listagem.
- **R6 — Tamanho de PR.** Inbox (718 linhas) e Visão geral (737) são grandes; fatiar em
  07a/07b e por seção da Visão geral se o diff exigir.
- **R7 — Duas fontes de verdade** entre `DESIGN.md` e `35-design-tokens.md`. Mitigação:
  `35` vira medição de contraste e cita o `DESIGN.md` como origem.
- **R8 — Marca.** O laranja substitui o lima que identifica o produto (logotipo `◉` em disco
  lima). Ajustar o logotipo é parte do F46-02. Decidido: o logotipo mantém sua cor
  original (D13); o acento laranja `#c2410c` fica só nos estados de UI (D14).

## 13. Decisões (2026-09-29)

Resolvidas em conversa com o usuário em 2026-09-29:

- **D8 — `page_size` variável na Inbox (Q1).** O slice F46-06 verifica se a API da Inbox
  aceita `page_size` (hoje constante 25 no cliente). Se aceitar, `PageSizeSelect` é
  integrado; se não, o seletor fica de fora e a fatia vira apenas `Pagination` com links
  numerados. `CompaniesPage` também é verificada no mesmo card: se já paginada, recebe
  `Pagination` nova; se não, continua sem paginação.
- **D9 — Teste visual sem baseline automatizado (Q2).** A SPEC propõe só checagem humana +
  screenshots capturados no Playwright e enviados ao CI; o baseline de screenshot (com
  revalidação a cada mudança de pixel) tem custo de manutenção. A jornada E2E continua
  rodando no CI sem baseline visual.
- **D10 — Remover o *eyebrow* (Q3).** O *eyebrow* ("Decisão diária") é removido do visual
  em F46-02. Se houver conteúdo significativo, migra para o subtítulo (slot `description`
  de `PageHeader`); se não, é descartado. Em Inbox, "Decisão diária" é um label de seção,
  não eyebrow.
- **D11 — Botão "Buscar" em `sr-only` (Q4).** O botão "Buscar" deixa de ser visível
  (classe `sr-only`); a lupa é clicável e a busca é acionada por Enter no campo. O F46-05
  implementa `SearchInput` com essa semântica.
- **D12 — "Buscas salvas" em dropdown (Q5).** "Buscas salvas" e "Salvar busca" são movidas
  para um dropdown ancorado à direita da `FilterBar` (ícone de marca/bookmark ou "Buscas
  salvas" com chevron). O layout exato é definido no F46-07 ao integrar na Inbox.
- **D13 — Logotipo mantém cor original (Q6).** O logotipo (disco e marca do Opportunity
  Radar) mantém sua cor atual (não muda para laranja). O acento laranja `#c2410c` é usado
  só para estados de UI (página atual, ativo, atenção), não para identidade visual do
  produto.
- **D14 — Laranja `#c2410c` confirmado (Q7).** O acento `#c2410c` é confirmado como valor
  final. Sua razão de contraste como texto (5.18:1 sobre `surface`, 4.71 sobre `canvas`)
  atende WCAG AA e está documentado em §4.3.
- **D15 — Faixa de abas do navegador fora de escopo (Q8).** Confirmado per D4: a
  reprodução da faixa de abas (Back, Forward, abas do navegador) é fora de escopo. O topo
  da sidebar usa o logotipo (R8); nenhuma aba de app é criada.
