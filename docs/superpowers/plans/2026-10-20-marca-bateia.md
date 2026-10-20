# Marca Bateia — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trocar a identidade de `apps/web` de "Opportunity Radar" (petróleo, Inter, só claro) para **Bateia**, direção Correnteza: tokens claro e escuro, fontes, logo e favicon, componentes, Inbox, detalhe da vaga, primeiro acesso e textos.

**Architecture:** Migração por valores: os tokens da SPEC 54 mantêm o nome em `styles.css` e trocam de valor; o tema escuro redefine os mesmos `--color-*` sob `prefers-color-scheme` e `data-theme`. Peças novas e pequenas (marca, régua de pepitas, preferência de tema) entram em `components/ui/`, `features/matching/` e `lib/`; as rotas só trocam composição e texto. Nenhuma mudança de API ou de backend.

**Tech Stack:** React 19, Vite 8, Tailwind CSS 4 (`@theme`), Vitest 5 + Testing Library, ESLint 10, `@fontsource` (Schibsted Grotesk variável, Young Serif).

**Spec:** [DESIGN.md](../../../DESIGN.md) (marca Bateia, 2026-10-20). Estudo de origem: [docs/research/2026-10-20-branding-concorrentes.md](../../research/2026-10-20-branding-concorrentes.md).

## Global Constraints

- Trabalho em `feat/marca-bateia`, criada a partir de `docs/marca-bateia`. Nada de push, PR, deploy ou publicação sem SIM explícito do dono.
- Toda mensagem de commit termina com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Verificação de cada tarefa: `npm run check` em `apps/web`, saída com exit 0. Relatar o número de arquivos e testes da saída.
- Nenhum hexadecimal literal em `.ts/.tsx` (lint `no-restricted-syntax`); toda cor nova vira token em `apps/web/src/styles.css`.
- Texto >= 4.5:1 e controle >= 3:1 nos dois temas, impostos por `apps/web/src/styles.test.ts`.
- Valores de token, raios, escala de texto e fontes: exatamente os de DESIGN.md §2, §3 e §7.
- Dourado (`nugget*`) só em pepitas, ponto do logo e veredito Alta prioridade (DESIGN.md §2).
- Única primitiva de acessibilidade: `@radix-ui/react-dialog@1.2.0`, atrás de wrapper em `components/ui/`.
- Textos em PT-BR na voz de DESIGN.md §8. Nome do produto na interface: "Bateia". Repositório, pacotes e nomes técnicos continuam `opportunity-radar`.
- Não ler `.env`; não registrar segredo em log, teste ou commit.
- JS inicial gzip não pode subir mais de 10% sobre a base atual (medida da SPEC 54: 150.07 kB). Fontes não contam como JS, mas o total de `.woff2` empacotado deve ser registrado no commit da tarefa 1.

## Review Focus

1. **Tema escuro sem `data-theme`, só pelo sistema:** toda tela legível. Teste: paridade entre o bloco `@media` e o bloco `[data-theme="dark"]` e contraste dos pares escuros (tarefa 1).
2. **Score ausente ou não numérico na Inbox:** a régua some e aparece "Sem avaliação"; nada de "NaN de 100". Teste na tarefa 3 (`nuggetsFromScore`) e na tarefa 4 (linha da Inbox).
3. **`localStorage` indisponível (janela privada, bloqueio):** a preferência de tema cai para "sistema" sem erro. Teste na tarefa 3 (`readThemePreference`).
4. **Avaliação sem fatores, ou só `NOT_APPLICABLE`:** o detalhe mostra "Nenhum fator avaliado", sem régua "0 de 0". Teste na tarefa 5.
5. **Título e empresa longos a 320px com régua e veredito:** sem rolagem horizontal; `break-anywhere` continua no título. Teste de classe na tarefa 4 e captura manual a 320px na tarefa 8.

---

### Task 1: Tokens, tema escuro e fontes

**Files:**
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/src/styles.test.ts`
- Modify: `apps/web/package.json`, `apps/web/package-lock.json`
- Modify: `docs/35-design-tokens.md`

**Interfaces:**
- Produces: tokens `--color-*` com os nomes atuais e valores claros de DESIGN.md §2; tokens novos `--color-nugget`, `--color-nugget-ink`, `--color-nugget-surface`; `--font-display`; blocos `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {…} }` e `:root[data-theme="dark"] {…}` com os valores escuros e `color-scheme: dark`. Utilitários Tailwind gerados: `bg-nugget`, `text-nugget-ink`, `bg-nugget-surface`, `font-display`.

- [ ] **Step 1: Escrever os testes que falham em `styles.test.ts`**

Adicionar `darkToken(name: string): string`, que lê o valor de `--color-${name}` dentro do bloco `:root[data-theme="dark"] { … }`. Adicionar ao fim de `TEXT_PAIRS` os pares `['nugget-ink', 'nugget-surface']`, `['nugget-ink', 'surface']`, `['nugget-ink', 'canvas']`; a `CONTROL_PAIRS`, `['nugget', 'surface']` e `['nugget', 'canvas']`. Novos testes:

```ts
it.each(TEXT_PAIRS)('tema escuro: texto %s sobre %s >= 4.5', (fg, bg) => {
  expect(contrastOf(darkToken(fg), darkToken(bg))).toBeGreaterThanOrEqual(4.5)
})
it.each(CONTROL_PAIRS)('tema escuro: controle %s sobre %s >= 3', (fg, bg) => {
  expect(contrastOf(darkToken(fg), darkToken(bg))).toBeGreaterThanOrEqual(3)
})
it('o bloco do sistema e o bloco data-theme escuro têm os mesmos valores', () => {
  expect(mediaDarkBlock()).toEqual(dataThemeDarkBlock())
})
it('usa a marca Bateia', () => {
  expect(token('accent')).toBe('#1E5B4B')
  expect(token('nugget')).toBe('#A87A12')
  expect(darkToken('accent')).toBe('#79C2A6')
  expect(css).toContain('"Schibsted Grotesk Variable"')
  expect(css).toContain('"Young Serif"')
  expect(css).not.toContain('Inter Variable')
})
```

`contrastOf(fgHex, bgHex)` é a função `contrast` atual reescrita para receber hex; `mediaDarkBlock()` e `dataThemeDarkBlock()` devolvem `Record<string, string>` com cada `--color-*` do bloco. Incluir `nugget`, `nugget-ink` e `nugget-surface` na lista do teste "declara os tokens novos".

- [ ] **Step 2: Rodar e ver falhar**

Run: `npx vitest run src/styles.test.ts` (em `apps/web`)
Expected: FAIL em "usa a marca Bateia" e nos testes do tema escuro (`token --color-… não encontrado` no bloco escuro).

- [ ] **Step 3: Instalar fontes e trocar valores**

`npm install @fontsource-variable/schibsted-grotesk@5.3.0 @fontsource/young-serif@5.3.0 && npm uninstall @fontsource-variable/inter`. Em `styles.css`: trocar o `@font-face` de Inter por dois (`"Schibsted Grotesk Variable"`, peso 400 900, arquivo `schibsted-grotesk-latin-wght-normal.woff2`; `"Young Serif"`, peso 400, arquivo `young-serif-latin-400-normal.woff2`), mesmo `unicode-range` e `font-display: swap`. `--font-sans: "Schibsted Grotesk Variable", ui-sans-serif, system-ui, sans-serif`; `--font-display: "Young Serif", Georgia, serif`. Valores claros, escuros, raios (`--radius-panel: 0.75rem`, `--radius-control: 0.5rem`, `--radius-chip: 999px`), `--shadow-overlay: 0 4px 16px rgb(14 20 18 / 0.16)` e `--text-page-title` (1.75rem / 2.25rem / 400 / -0.01em) de DESIGN.md §2 e §3. Os blocos escuros ficam fora de `@theme`, depois dele. Atualizar o comentário do anel de foco para "verde-rio".

- [ ] **Step 4: Rodar e ver passar**

Run: `npx vitest run src/styles.test.ts`
Expected: PASS, todos os pares nos dois temas.

- [ ] **Step 5: Atualizar `docs/35-design-tokens.md`**

Tabelas de superfície, texto, semânticos e contraste com colunas Claro e Escuro e a razão medida de cada par (o teste imprime os valores; copiar com duas casas). Seção "Ajustes registrados": dourado claro escurecido de `#C8961E` para `#A87A12` para chegar a 3:1 sobre `canvas`.

- [ ] **Step 6: Verificar o pacote inteiro**

Run: `npm run check`
Expected: exit 0. Telas antigas mudam de cor e fonte; nenhum teste de componente deve quebrar (as classes não mudaram). Registrar o JS gzip e o tamanho dos `.woff2` em `dist/assets`.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/styles.css apps/web/src/styles.test.ts apps/web/package.json apps/web/package-lock.json docs/35-design-tokens.md
git commit -m "feat(web): Bateia tokens, dark theme and self-hosted fonts"
```

### Task 2: Logo, ícone e favicon

**Files:**
- Create: `apps/web/src/components/ui/BrandMark.tsx`
- Create: `apps/web/src/components/ui/BrandMark.test.tsx`
- Create: `apps/web/public/favicon.svg`, `apps/web/public/icon-32.png`, `apps/web/public/apple-touch-icon.png` (180), `apps/web/public/icon-192.png`, `apps/web/public/icon-512.png`, `apps/web/public/site.webmanifest`
- Modify: `apps/web/index.html`

**Interfaces:**
- Produces: `BrandSymbol({ size = 28, className }: { size?: number; className?: string })` e `BrandMark({ className }: { className?: string })` (símbolo + wordmark `bateia`). Cores só por `currentColor` e classes `text-brand` / `fill-nugget`; `BrandSymbol` tem `aria-hidden="true"`; `BrandMark` expõe o nome "Bateia" a leitores de tela.

- [ ] **Step 1: Teste que falha**

```tsx
it('desenha três anéis e uma pepita na posição fixa', () => {
  const { container } = render(<BrandSymbol />)
  expect(container.querySelectorAll('circle[fill="none"]')).toHaveLength(3)
  const nugget = container.querySelector('circle.fill-nugget')
  expect(nugget).toHaveAttribute('cx', '21.5')
  expect(nugget).toHaveAttribute('cy', '11')
})
it('o wordmark é lido como Bateia', () => {
  render(<BrandMark />)
  expect(screen.getByText('bateia')).toHaveClass('font-display')
  expect(screen.getByLabelText('Bateia')).toBeInTheDocument()
})
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npx vitest run src/components/ui/BrandMark.test.tsx`
Expected: FAIL, módulo não encontrado.

- [ ] **Step 3: Implementar** com a geometria de DESIGN.md §4: grade 32, anéis de raio 14, 9 e 4, traço 2, pepita de raio 2.8 em (21.5, 11).

- [ ] **Step 4: Favicon e manifest.** `favicon.svg` é o ícone do app (quadrado com cantos de 22% em `#1E5B4B`, anéis `#FAFBF8`, pepita `#A87A12`; hex permitido aqui porque não é `.ts/.tsx`) com `@media (prefers-color-scheme: dark)` interno trocando fundo para `#161E1B` e anéis para `#79C2A6`. PNGs exportados do mesmo SVG; em 32px, sem o anel interno. `index.html`: `<title>Bateia</title>`, `<meta name="theme-color" content="#ECEEEA" media="(prefers-color-scheme: light)">`, outra com `#0E1412` para escuro, `<link rel="icon" href="/favicon.svg" type="image/svg+xml">`, `<link rel="icon" href="/icon-32.png" sizes="32x32">`, `<link rel="apple-touch-icon" href="/apple-touch-icon.png">`, `<link rel="manifest" href="/site.webmanifest">`. Manifest com `name: "Bateia"`, `short_name: "Bateia"`, ícones 192 e 512, `theme_color: "#1E5B4B"`, `background_color: "#ECEEEA"`.

- [ ] **Step 5: Verificar**

Run: `npm run check`
Expected: exit 0; `dist/` contém `favicon.svg` e `site.webmanifest`.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/ui/BrandMark.tsx apps/web/src/components/ui/BrandMark.test.tsx apps/web/public apps/web/index.html
git commit -m "feat(web): Bateia logo, app icon and favicon"
```

### Task 3: Componentes de base, régua de pepitas e preferência de tema

**Files:**
- Create: `apps/web/src/features/matching/nuggets.ts`, `apps/web/src/features/matching/nuggets.test.ts`
- Create: `apps/web/src/components/ui/NuggetMeter.tsx`, `apps/web/src/components/ui/NuggetMeter.test.tsx`
- Create: `apps/web/src/lib/theme.ts`, `apps/web/src/lib/theme.test.ts`
- Create: `apps/web/src/components/ui/ThemeToggle.tsx`, `apps/web/src/components/ui/ThemeToggle.test.tsx`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/src/features/matching/verdicts.ts`
- Modify: `apps/web/src/components/Sidebar.tsx`, `apps/web/src/components/Sidebar.test.tsx`
- Modify: `apps/web/src/components/PageHeader.tsx`, `apps/web/src/components/PageHeader.test.tsx`

**Interfaces:**
- Consumes: `BrandMark` (tarefa 2); tokens `nugget*`, `font-display` (tarefa 1); `MatchFactor` de `features/matching/api.ts`.
- Produces:
  - `nuggetsFromScore(score: string | null): number | null` — `null` se `score` é `null` ou não numérico; senão `Math.round(clamp(Number(score), 0, 100) / 10)`.
  - `countFactors(factors: MatchFactor[]): { met: number; missed: number; unknown: number }` — ignora `NOT_APPLICABLE`; `met` = `KNOWN` com `Number(rawScore) >= 0.5`; `missed` = `KNOWN` com `rawScore < 0.5` ou `null`; `unknown` = `UNKNOWN`.
  - `NuggetMeter({ met, missed = 0, unknown = 0, label }: { met: number; missed?: number; unknown?: number; label: string })` — `met + missed + unknown` pepitas na ordem cheia, vazada, tracejada; contêiner `role="img"` com `aria-label={label}` e o `label` também visível em `text-caption`.
  - `type ThemePreference = 'system' | 'light' | 'dark'`; `readThemePreference(): ThemePreference` (chave `bateia-theme`, `try/catch`, valor inválido vira `'system'`); `writeThemePreference(p: ThemePreference): void`; `applyThemePreference(p: ThemePreference, root = document.documentElement): void` (`'system'` remove `data-theme`).
  - `ThemeToggle()` — grupo de três botões "Sistema", "Claro", "Escuro" com `aria-pressed`.
  - `verdictTones.HIGH_PRIORITY = 'border-nugget bg-nugget-surface text-nugget-ink'`; demais tons conforme DESIGN.md §5.

- [ ] **Step 1: Testes que falham**

```ts
// nuggets.test.ts
expect(nuggetsFromScore('76.0')).toBe(8)
expect(nuggetsFromScore('4.9')).toBe(0)
expect(nuggetsFromScore('130')).toBe(10)
expect(nuggetsFromScore(null)).toBeNull()
expect(nuggetsFromScore('n/d')).toBeNull()
expect(countFactors([
  factor('KNOWN', '0.9'), factor('KNOWN', '0.2'), factor('KNOWN', null),
  factor('UNKNOWN', null), factor('NOT_APPLICABLE', null),
])).toEqual({ met: 1, missed: 2, unknown: 1 })
expect(countFactors([factor('NOT_APPLICABLE', null)])).toEqual({ met: 0, missed: 0, unknown: 0 })

// theme.test.ts
it('cai para system quando localStorage lança', () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
  expect(readThemePreference()).toBe('system')
})
it('system remove data-theme; dark define', () => {
  const root = document.createElement('html')
  applyThemePreference('dark', root); expect(root.dataset.theme).toBe('dark')
  applyThemePreference('system', root); expect(root.hasAttribute('data-theme')).toBe(false)
})

// NuggetMeter.test.tsx
render(<NuggetMeter met={6} missed={2} unknown={1} label="6 de 9 fatores atendidos, 1 sem dado" />)
expect(screen.getByRole('img', { name: '6 de 9 fatores atendidos, 1 sem dado' })).toBeInTheDocument()
expect(screen.getByText('6 de 9 fatores atendidos, 1 sem dado')).toBeVisible()
expect(document.querySelectorAll('[data-nugget="met"]')).toHaveLength(6)
expect(document.querySelectorAll('[data-nugget="unknown"]')).toHaveLength(1)

// Sidebar.test.tsx (acrescentar)
expect(screen.getByLabelText('Bateia')).toBeInTheDocument()
expect(screen.getByText('A IA roda no seu computador. Nenhuma empresa vê seu perfil aqui.')).toBeInTheDocument()
expect(screen.getByRole('group', { name: 'Tema' })).toBeInTheDocument()

// PageHeader.test.tsx (acrescentar)
expect(screen.getByRole('heading', { level: 1 })).toHaveClass('font-display')
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `npx vitest run src/features/matching/nuggets.test.ts src/lib/theme.test.ts src/components`
Expected: FAIL nos módulos novos e nas asserções novas de Sidebar e PageHeader.

- [ ] **Step 3: Implementar** as assinaturas acima. `main.tsx` chama `applyThemePreference(readThemePreference())` antes do `createRoot`. Sidebar: `BrandMark` no topo, rótulos de grupo em `text-caption font-semibold` sem `uppercase` nem `tracking-*`, nota de privacidade no rodapé com o texto do teste, `ThemeToggle` com `role="group"` e `aria-label="Tema"`. PageHeader: `h1` com `font-display text-page-title`.

A frase de privacidade só é verdadeira com a IA local (Ollama). Antes de implementar, confirmar com o dono se o ambiente hospedado da F53 mantém a IA local; se não mantiver, o texto vira "Nenhuma empresa vê seu perfil aqui." e o teste acompanha.

- [ ] **Step 4: Rodar e ver passar**

Run: `npm run check`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/features/matching apps/web/src/components apps/web/src/lib/theme.ts apps/web/src/lib/theme.test.ts apps/web/src/main.tsx
git commit -m "feat(web): nugget meter, theme preference and Bateia sidebar"
```

### Task 4: Inbox

**Files:**
- Modify: `apps/web/src/routes/InboxPage.tsx`
- Modify: `apps/web/src/routes/InboxPage.test.tsx`

**Interfaces:**
- Consumes: `nuggetsFromScore`, `NuggetMeter`, `verdictTones` (tarefa 3).

- [ ] **Step 1: Testes que falham** (acrescentar ao arquivo existente)

```tsx
it('mostra a régua de pepitas a partir do score', async () => {
  renderInbox([item({ score: '76.0', verdict: 'HIGH_PRIORITY' })])
  expect(await screen.findByRole('img', { name: '76 de 100' })).toBeInTheDocument()
})
it('sem score, não mostra régua e diz Sem avaliação', async () => {
  renderInbox([item({ score: null, verdict: null })])
  expect(await screen.findByText('Sem avaliação')).toBeInTheDocument()
  expect(screen.queryByRole('img', { name: /de 100/ })).toBeNull()
})
it('mostra o resumo da IA como motivo e não inventa motivo sem ele', async () => {
  renderInbox([item({ analysisSummary: null })])
  expect(await screen.findByRole('row')).not.toHaveTextContent('Por que')
})
it('título longo continua quebrando dentro da linha', async () => {
  renderInbox([item({ title: 'A'.repeat(200) })])
  expect((await screen.findByRole('link', { name: 'A'.repeat(200) })).closest('.break-anywhere')).not.toBeNull()
})
```

`renderInbox` e `item` são os ajudantes já usados em `InboxPage.test.tsx`; se tiverem outro nome, usar o existente.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npx vitest run src/routes/InboxPage.test.tsx`
Expected: FAIL nos quatro testes novos (os três primeiros por ausência de régua e texto).

- [ ] **Step 3: Implementar.** Trocar `ScoreBox` por `NuggetMeter` com `met = nuggetsFromScore(score)`, `missed = 10 - met`, `label = "<score arredondado> de 100"`; sem score, texto "Sem avaliação" em `text-muted`. Ordem da célula: régua, veredito, candidatura. O resumo da IA vem logo abaixo de empresa e local, em `text-ink`. Cabeçalho da página: título "Inbox" e subtítulo "<n> vagas para decidir." (o "de 214 coletadas" do mock depende de um contador que a API da Inbox não expõe; fica fora). Avisos de avaliação desatualizada e IA indisponível mudam de texto na tarefa 7, não aqui. Atualizar asserções antigas que procuravam o `ScoreBox` (`"76.0"`) para o novo rótulo.

- [ ] **Step 4: Rodar e ver passar**

Run: `npm run check`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/InboxPage.tsx apps/web/src/routes/InboxPage.test.tsx
git commit -m "feat(web): Bateia inbox row with nugget meter"
```

### Task 5: Detalhe da vaga

**Files:**
- Modify: `apps/web/src/routes/OpportunityDetailPage.tsx`
- Modify: `apps/web/src/routes/OpportunityDetailPage.test.tsx`

**Interfaces:**
- Consumes: `countFactors`, `NuggetMeter` (tarefa 3); `MatchAssessment.factors` e filtros eliminatórios já carregados pela página.

- [ ] **Step 1: Testes que falham**

```tsx
it('resume os fatores em pepitas', async () => {
  renderDetail({ factors: [known('0.9'), known('0.8'), known('0.1'), unknown()] })
  expect(await screen.findByRole('img', { name: '2 de 4 fatores atendidos, 1 sem dado' })).toBeInTheDocument()
})
it('sem fatores aplicáveis, diz Nenhum fator avaliado', async () => {
  renderDetail({ factors: [notApplicable()] })
  expect(await screen.findByText('Nenhum fator avaliado')).toBeInTheDocument()
  expect(screen.queryByRole('img', { name: /fatores atendidos/ })).toBeNull()
})
it('mostra O que impede antes de Por que combina', async () => {
  renderDetail({ eligibility: [failedFilter()] })
  const headings = (await screen.findAllByRole('heading')).map((h) => h.textContent)
  expect(headings.indexOf('O que impede')).toBeLessThan(headings.indexOf('Por que combina'))
})
```

Fábricas `known`, `unknown`, `notApplicable`, `failedFilter` montam `MatchFactor` / `EligibilityDetail` com os campos do tipo; criar no próprio arquivo de teste.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npx vitest run src/routes/OpportunityDetailPage.test.tsx`
Expected: FAIL nos três testes.

- [ ] **Step 3: Implementar.** Seção "Fatores do score" vira "Por que combina": régua no topo com `countFactors` e rótulo `"<met> de <met+missed+unknown> fatores atendidos"` + `", <unknown> sem dado"` quando `unknown > 0`; cada fator em lista com ✓ (atendido, `text-success-ink`), − (faltante, `text-warning-ink`) ou ? (sem dado, `text-muted`) e a `explanation`. "Filtros eliminatórios" vira "O que impede" e vem antes. Título da vaga em `font-display`. Veredito Alta prioridade usa o tom `nugget`. Não alterar o painel de decisão nem a ordem DOM = ordem visual da SPEC 54.

- [ ] **Step 4: Rodar e ver passar**

Run: `npm run check`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/OpportunityDetailPage.tsx apps/web/src/routes/OpportunityDetailPage.test.tsx
git commit -m "feat(web): explained match on the opportunity detail"
```

### Task 6: Primeiro acesso e landing

**Files:**
- Create: `apps/web/src/components/FirstRunGuide.tsx`, `apps/web/src/components/FirstRunGuide.test.tsx`
- Modify: `apps/web/src/routes/OverviewPage.tsx`, `apps/web/src/routes/OverviewPage.test.tsx`
- Modify: `apps/web/src/routes/InboxPage.tsx`, `apps/web/src/routes/InboxPage.test.tsx`
- Modify: `apps/web/src/routes/LandingPage.tsx`

**Interfaces:**
- Consumes: `getActiveProfile(): Promise<ProfileVersion | null>` (já existe; `null` quando a API responde 404); `BrandMark`.
- Produces: `FirstRunGuide()` — painel com título em `font-display` "Monte sua bateia" e três passos ligados a `/profile`: "Diga o que você procura" (cargo, senioridade, regime), "Marque o que é exigido" (skills), "Defina seu mínimo" (salário e local). Botão "Começar pelo perfil".

- [ ] **Step 1: Testes que falham**

```tsx
it('sem perfil, a Visão geral mostra o primeiro acesso', async () => {
  mockActiveProfile(null)
  renderOverview()
  expect(await screen.findByRole('heading', { name: 'Monte sua bateia' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Começar pelo perfil' })).toHaveAttribute('href', '/profile')
})
it('com perfil, o primeiro acesso não aparece', async () => {
  mockActiveProfile(profileVersion())
  renderOverview()
  await screen.findByRole('heading', { level: 1 })
  expect(screen.queryByRole('heading', { name: 'Monte sua bateia' })).toBeNull()
})
```

O mesmo par de testes na Inbox, onde o guia substitui a lista vazia.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npx vitest run src/components/FirstRunGuide.test.tsx src/routes/OverviewPage.test.tsx src/routes/InboxPage.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implementar.** Overview e Inbox consultam o perfil com a query React Query já usada pela página de Perfil (mesma `queryKey`, para não duplicar requisição) e mostram `FirstRunGuide` quando o resultado é `null`. Falha ao carregar o perfil não mostra o guia (o estado de erro existente continua). Landing: `BrandMark` no lugar do nome, hero "Menos vagas, cada uma com o porquê.", subtítulo sobre match explicado, IA e privacidade, sem campo de busca nem contagem de vagas; FAQ troca "Opportunity Radar" por "Bateia".

- [ ] **Step 4: Rodar e ver passar**

Run: `npm run check`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/FirstRunGuide.tsx apps/web/src/components/FirstRunGuide.test.tsx apps/web/src/routes/OverviewPage.tsx apps/web/src/routes/OverviewPage.test.tsx apps/web/src/routes/InboxPage.tsx apps/web/src/routes/InboxPage.test.tsx apps/web/src/routes/LandingPage.tsx
git commit -m "feat(web): first-run guide and Bateia landing"
```

### Task 7: Textos da interface

**Files:**
- Modify: `apps/web/src/app/App.tsx`, `apps/web/src/app/App.test.tsx`
- Modify: `apps/web/src/routes/InboxPage.tsx`, `apps/web/src/routes/OpportunityDetailPage.tsx`, `apps/web/src/routes/OverviewPage.tsx` e seus testes
- Modify: `apps/web/src/features/matching/AnalysisPanel.tsx`
- Modify: `apps/web/src/components/states.tsx`, `apps/web/src/components/states.test.tsx`

**Interfaces:**
- Consumes: tabela "Em vez de / Escreva" e exemplos de DESIGN.md §8.

- [ ] **Step 1: Teste-guarda que falha.** Criar `apps/web/src/copy.test.ts`, que lê todos os `.tsx` de `src/routes`, `src/components` e `src/features` (exceto `*.test.tsx`) e falha se encontrar `Opportunity Radar`, `Análise semântica`, `Fatores do score`, `Filtros eliminatórios`, `Procedência` ou `decisão determinística` em texto renderizado.

Run: `npx vitest run src/copy.test.ts`
Expected: FAIL listando arquivo e termo.

- [ ] **Step 2: Trocar os textos** pela tabela de DESIGN.md §8. Código técnico de status (`AI_FAILED` e similares) sai da frase principal e vai para um `<details>` "Detalhe técnico". Estado vazio da Inbox: "Nada novo para decidir. A próxima coleta acontece no próximo ciclo." (o horário exato só entra se a API expuser o agendamento). Atualizar as asserções de texto dos testes existentes no mesmo passo.

- [ ] **Step 3: Rodar e ver passar**

Run: `npm run check`
Expected: exit 0, incluindo `copy.test.ts`.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src
git commit -m "feat(web): Bateia voice across the interface"
```

### Task 8: Conferência visual e de pacote

**Files:**
- Modify: `docs/54-review/README.md` (seção nova "Marca Bateia")

- [ ] **Step 1:** `npm run build` e anotar JS inicial gzip e total de `.woff2`; comparar com 150.07 kB (limite +10%).
- [ ] **Step 2:** Rodar a captura existente da SPEC 54 (11 caminhos × 5 larguras) nos temas claro e escuro, incluindo 320px; conferir que não há rolagem horizontal e que régua, veredito e título longo cabem.
- [ ] **Step 3:** Registrar resultado, números e o que não foi verificado (leitor de tela, zoom real, aparelho físico, E2E com Docker) no README de revisão.
- [ ] **Step 4: Commit**

```bash
git add docs/54-review/README.md
git commit -m "docs(review): Bateia visual and bundle check"
```

## Fora deste plano

- Motivo determinístico por vaga e contador "coletadas desde ontem" na API da Inbox (mudança de backend).
- Renomear repositório, domínio e handle (getbateia.com, bateia-app); busca de marca no INPI.
- Telas WP5 da SPEC 54 ainda não migradas (Empresas, Fontes, Homologação, Perfil, Status): recebem tokens e fonte automaticamente pela tarefa 1, sem revisão de composição.
