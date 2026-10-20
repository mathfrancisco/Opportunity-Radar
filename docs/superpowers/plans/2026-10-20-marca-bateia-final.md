# Marca Bateia — finalização: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fechar a marca Bateia: minors adiados que ainda valem, composição Bateia nas telas WP5, motivo e contador da Inbox vindos do backend, conferência final no app real, e um checklist do que só o dono pode fazer.

**Architecture:** Quatro áreas num só branch `feat/marca-bateia-final` a partir de `origin/main` (184fb95). As tarefas de backend (Área C, T10-T11) tocam só `src/` e `tests/` e ficam em commits próprios, para poderem virar um PR separado por cherry-pick se o dono preferir. O motivo determinístico é calculado na consulta da Inbox a partir de `match_factor` já gravado; nenhuma coluna nova, então nenhuma migration é esperada.

**Tech Stack:** React 19 + Vite + Tailwind v4 + Vitest (react-dom/client + act, sem @testing-library) em `apps/web`; Python 3 + FastAPI + SQLAlchemy + pytest no backend; `@clerk/react` 6.x.

**Spec:** `DESIGN.md` (§0 princípios, §3 tipografia, §4 logo, §5 match explicado, §6 regras, §8 voz). Ledger anterior com minors e rulings: `.superpowers/sdd/2026-10-20-marca-bateia/progress.md` (local).

## Global Constraints

- Texto da UI diz "vaga", nunca "oportunidade" (`apps/web/src/copy.test.ts`). PT-BR na voz da §8: frase curta, sem exclamação, sem "ops", hora com "h".
- Código técnico (`AI_FAILED`, `HIGH_PRIORITY`, `COUNTRY_ALLOWED`, ids, versões) não aparece no texto principal; vai para `<details>` "Detalhe técnico" quando for útil.
- Privacidade: só afirmar o que é verdade. A IA roda na nuvem (Groq; Token Harbor de reserva) e recebe o perfil sem os contatos. Nota atual "Nenhum recrutador vê seu perfil aqui." continua.
- Nenhum hexadecimal literal em `.ts/.tsx`; cor nova vira token em `apps/web/src/styles.css` nos três blocos (claro, escuro por media query, `data-theme="dark"`).
- Young Serif só a partir de 1.5rem. Rótulos não usam caixa alta com tracking largo.
- Nenhuma dependência nova. Nunca rodar `npm install` local em `apps/web`; se o lock precisar mudar, editar a partir do de `main` e validar com `npm ci --dry-run` numa pasta temporária.
- Verificação web: `npm run check` em `apps/web` com exit 0; reportar arquivos de teste, testes e JS gzip (base 215,83 kB, limite 237,4 kB).
- Verificação backend: `ruff check`, `ruff format --check`, `mypy` (se configurado em `pyproject.toml`) e `pytest` dos módulos tocados; integração com Postgres via o padrão de `tests/backend/conftest.py`.
- Não ler `.env` nem `apps/web/.env.local`. Nada de push, PR, merge ou deploy sem SIM do dono.
- Commits terminam com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. `localStorage` bloqueado (Safari privado, cookies desligados): o script inline do `<head>` lança e a página precisa abrir no tema do sistema, sem erro no console que quebre o resto. Teste em T1.
2. Gaveta móvel aberta com a sidebar `md+` também montada: os dois `ThemeToggle` mostram o mesmo `aria-pressed` depois de um clique em qualquer um. Teste em T1.
3. Vaga com avaliação desatualizada ou de outra versão de perfil: o motivo vem só do ponteiro de avaliação atual que a Inbox já usa; vaga sem fator `KNOWN` com `raw_score >= 0.5` tem motivo `null`, nunca um fator faltante. Teste em T10.
4. Contador e motivo isolados por `owner_sub`: avaliações de outra pessoa não entram na contagem nem no motivo. Teste em T11 (e T10).
5. Virada do dia: "desde ontem" é o início de ontem em `America/Sao_Paulo`, não em UTC; uma vaga vista às 22h de anteontem em São Paulo (01h UTC de ontem) não conta. Teste em T11.

---

## Área A — Minors adiados (web)

Cada implementador confere o minor no código antes de mexer; minor já resolvido vira linha "já resolvido em <commit>" no relatório, sem diff.

### Task 1: Tema sem flash e ThemeToggle sincronizado

**Files:**
- Modify: `apps/web/index.html`, `apps/web/src/lib/theme.ts`, `apps/web/src/components/ui/ThemeToggle.tsx`
- Test: `apps/web/src/lib/theme.test.ts`, `apps/web/src/components/ui/ThemeToggle.test.tsx`, novo `apps/web/src/indexHtml.test.ts`

**Interfaces:**
- Produces: `subscribeThemePreference(listener: () => void): () => void` e evento `bateia-theme-change` disparado por `writeThemePreference`; `applyThemePreference(preference, root?)` também ajusta as duas `<meta name="theme-color">`.

- [ ] **Step 1: Testes que falham**
  - `indexHtml.test.ts` lê `apps/web/index.html` (fs) e afirma: existe um `<script>` inline antes de `<link rel="manifest">`, que lê a chave `bateia-theme`, aplica `data-theme` só para `light`/`dark` e está dentro de `try { … } catch`. Executar o corpo do script com `localStorage.getItem` lançando não lança e não define `data-theme`.
  - `theme.test.ts`: `applyThemePreference('dark')` deixa as duas metas `theme-color` com o valor do `canvas` escuro; `'light'` com o claro; `'system'` restaura o claro na meta `(prefers-color-scheme: light)` e o escuro na `(prefers-color-scheme: dark)`. Os valores vêm de `getComputedStyle`/constantes lidas do `index.html` no teste, nunca hex literal em `.ts` (comparar sem `#`, como no ruling de T1 anterior).
  - `ThemeToggle.test.tsx`: monta dois `ThemeToggle`; clicar "Escuro" no primeiro deixa `aria-pressed="true"` em "Escuro" nos dois.
- [ ] **Step 2: Rodar e ver falhar** — `npx vitest run src/lib/theme.test.ts src/components/ui/ThemeToggle.test.tsx src/indexHtml.test.ts` → FAIL.
- [ ] **Step 3: Implementar.** Script inline mínimo no `<head>` (sem hex novo em `.ts`; os hex das metas ficam no HTML). `ThemeToggle` usa `useSyncExternalStore(subscribeThemePreference, readThemePreference)`. As cores das metas: `theme.ts` lê o `content` original de cada meta na primeira chamada (guardado em `data-default`) e copia o da meta do tema forçado para as duas.
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** `fix(web): apply theme before paint and keep toggles in sync`.

### Task 2: Ícones e wordmark

**Files:**
- Modify: `apps/web/public/apple-touch-icon.png`, `apps/web/public/site.webmanifest`, `apps/web/src/components/ui/BrandMark.tsx`, `DESIGN.md` §4
- Create: `apps/web/public/icon-maskable-512.png`
- Test: `apps/web/src/components/ui/BrandMark.test.tsx`, novo `apps/web/src/manifest.test.ts`

- [ ] **Step 1: Testes que falham**
  - `manifest.test.ts`: o manifest tem um ícone `"purpose": "maskable"` de 512x512 apontando para `/icon-maskable-512.png`, e o arquivo existe; `apple-touch-icon.png` tem 180x180 e o pixel (0,0) é opaco (ler o cabeçalho PNG/IDAT com `zlib` do Node, sem dependência).
  - `BrandMark.test.tsx`: o wordmark é encontrado por `querySelector('.font-display')` (sem a busca indireta atual) e tem a classe `text-2xl`.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** Rasterizar com `@resvg/resvg-js@2.6.2` numa pasta temporária fora do repo (ruling anterior; não vira dependência). apple-touch: quadrado cheio em `brand`, sem cantos transparentes. Maskable: mesmo desenho com os anéis dentro de 80% do centro (zona segura). Wordmark `text-2xl` (1.5rem, mínimo da §3). Atualizar §4: "wordmark em 1.5rem ao lado do símbolo de 28px; a regra de altura do x vale para o logo em arte, não para a interface" — **ruling a confirmar pelo dono** (a regra antiga pede ~28px de fonte, grande demais para a sidebar).
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** `fix(web): full-bleed touch icon, maskable icon, wordmark at 1.5rem`.

### Task 3: NuggetMeter acessível e robusto

**Files:**
- Modify: `apps/web/src/components/ui/NuggetMeter.tsx`
- Test: `apps/web/src/components/ui/NuggetMeter.test.tsx`

- [ ] **Step 1: Testes que falham** — o texto visível tem `aria-hidden="true"` e o `role="img"` mantém o `aria-label`, então o rótulo aparece uma vez na árvore acessível; `met={NaN}`, `met={2.6}` e `missed={-1}` não lançam e renderizam `floor` de valores finitos não negativos (NaN → 0). Trocar os rótulos descartáveis dos testes atuais por rótulos reais ("6 de 9 fatores atendidos, 1 sem dado", "76 de 100").
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** com um helper local `count(n: number): number` (`Number.isFinite(n) ? Math.max(0, Math.floor(n)) : 0`).
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** `fix(web): announce nugget meter once and guard non-integer counts`.

### Task 4: Textos, rótulos e tokens soltos

**Files:**
- Modify: `apps/web/src/routes/LandingPage.tsx`, `apps/web/src/app/App.tsx`, `apps/web/src/routes/InboxPage.tsx`, `apps/web/src/routes/OpportunityDetailPage.tsx`, `apps/web/src/styles.css`, `apps/web/src/copy.test.ts`, `docs/35-design-tokens.md`
- Test: `apps/web/src/copy.test.ts`, `apps/web/src/styles.test.ts`, `apps/web/src/routes/InboxPage.test.tsx`, `apps/web/src/routes/LandingPage.test.tsx`

- [ ] **Step 1: Testes que falham**
  - `copy.test.ts`: nenhum `.tsx` em `src/routes`, `src/app`, `src/components` contém a classe `uppercase` junto de `tracking-[`; nenhum texto renderizado contém "análise por IA" (case-insensitive). O stripper de comentários só remove `//` quando a linha começa com espaços seguidos de `//` **fora** de string/JSX (corrigir o minor de T7: hoje descarta qualquer linha que começa com `//`).
  - `styles.test.ts`: todo `--color-*` do bloco claro existe nos dois blocos escuros; `--color-info-line` existe nos três blocos e tem >= 3:1 sobre `info-surface` nos dois temas.
  - `InboxPage.test.tsx`: com `total = 6`, a frase "6 vagas" aparece uma vez só na página; linha sem score e sem veredito mostra só o chip "Não avaliada" (sem "Sem avaliação"); linha com veredito e sem score mostra "Sem avaliação".
  - `LandingPage.test.tsx`: FAQ contém "A leitura da IA, quando disponível".
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** Rótulos de seção da landing e do App.tsx viram `text-caption font-semibold text-accent-ink` em caixa normal. Inbox: manter só o cabeçalho de resultados (linha ~979) e remover a repetição do subtítulo (linha ~651), ou o inverso, desde que a frase apareça uma vez; T12 troca esse texto pelo contador. `ScoreMeter` recebe `verdict` e retorna `null` quando os dois faltam; tira o `score === null` redundante e o parse duplicado. Token `info-line` (claro próximo de `#A9BFC5`, escuro próximo de `#3D5A62`, ajustar até passar o teste). `:focus-visible` usa `border-radius: inherit`.
- [ ] **Step 4: Rodar e ver passar.**
- [ ] **Step 5: Commit** `fix(web): sentence-case labels, single Inbox count, info-line token`.

### Task 5: Clerk no tema da Bateia

**Files:**
- Create: `apps/web/src/app/clerkAppearance.ts`
- Modify: `apps/web/src/app/WebApplication.tsx`
- Test: novo `apps/web/src/app/clerkAppearance.test.ts`

**Interfaces:**
- Produces: `export const clerkAppearance: Appearance` (tipo de `@clerk/react` ou `@clerk/types`, conforme o pacote já instalado expõe).

- [ ] **Step 1: Confirmar no Context7** (`@clerk/react` 6.x) que `appearance.variables` aceita `var(--…)` e quais chaves existem (`colorPrimary`, `colorBackground`, `colorText`, `colorTextSecondary`, `colorInputBackground`, `colorInputText`, `colorDanger`, `borderRadius`, `fontFamily`). Se não aceitar CSS vars, parar e reportar `NEEDS_CONTEXT` (não instalar `@clerk/themes`).
- [ ] **Step 2: Teste que falha** — todo valor de `clerkAppearance.variables` é `var(--color-…)`/`var(--font-…)`/`var(--radius-…)` de token existente em `styles.css` (o teste lê o CSS), e não há hex.
- [ ] **Step 3: Implementar** e passar `appearance={clerkAppearance}` ao `ClerkProvider` (cobre SignIn, SignUp e UserButton).
- [ ] **Step 4: Rodar e ver passar; `npm run build` e anotar o gzip.**
- [ ] **Step 5: Commit** `feat(web): theme Clerk components with Bateia tokens`.

### Task 6: Testes fracos do ledger

**Files:** `apps/web/src/routes/OverviewPage.test.tsx`, `apps/web/src/routes/InboxPage.test.tsx`, `apps/web/src/app/App.test.tsx`, `apps/web/src/routes/OpportunityDetailPage.test.tsx`

- [ ] **Step 1:** Overview: a metade "carregando" do teste sem guia espera o fetch pendente de forma explícita (promise controlada) e afirma o skeleton antes de resolver.
- [ ] **Step 2:** Inbox: erro ao carregar o perfil não mostra `FirstRunGuide` e mostra a lista (ou o estado de erro da lista).
- [ ] **Step 3:** App: cabeçalho público tem `role="img"` com nome "Bateia".
- [ ] **Step 4:** Detalhe: IA indisponível usa classes neutras (`bg-panel`/`text-subtle`, sem `danger-*`/`warning-*`).
- [ ] **Step 5:** Rodar os quatro arquivos; cada teste novo deve falhar se a asserção principal for invertida (o revisor confere). Commit `test(web): tighten deferred weak assertions`.

---

## Área B — Telas WP5 (web)

Regras comuns a T7-T9: título por `PageHeader` (Young Serif), subtítulo de uma frase na voz §8, os quatro estados (carregando com skeleton, vazio com próximo passo, erro com o que continua valendo, parcial quando parte dos dados falha), rótulos pt-BR por mapa local ou de `features/*`, código técnico só em `<details><summary>Detalhe técnico</summary>`. Cada tela é conferida nos dois temas pelo teste de classes (sem cor por tema no componente). Testes por tela: um teste por estado + um teste "nenhum `[A-Z]{3,}_[A-Z_]+` no texto visível fora de `<details>`" usando um helper novo `visibleTextOutsideDetails(container): string` em `apps/web/src/components/testing.tsx`.

### Task 7: Empresas (lista e detalhe)

**Files:** `apps/web/src/routes/CompaniesPage.tsx`, `apps/web/src/routes/CompanyDetailPage.tsx` e testes.
- [ ] Veredito cru (`CompanyDetailPage.tsx:244`, `item.verdict ?? 'não avaliada'`) vira `VerdictBadge`/`verdictLabels` com `verdictTones`; prioridade e status de fonte da empresa com rótulo pt-BR.
- [ ] Estados e teste de códigos; commit `feat(web): Bateia composition for companies`.

### Task 8: Fontes e Status

**Files:** `apps/web/src/routes/SourcesPage.tsx`, `apps/web/src/routes/StatusPage.tsx`, `apps/web/src/components/SourceControlsPanel.tsx` e testes.
- [ ] Falha de fonte no formato da §8 ("A Gupy não respondeu. Tentamos de novo às 14h10.") quando os dados trazem nome e próxima tentativa; sem próxima tentativa, só a primeira frase. Hora formatada por um helper `formatHour(date: Date): string` → "14h10", "6h" em `apps/web/src/lib/time.ts` (novo, com teste).
- [ ] Status: API indisponível em tom neutro, com o que continua valendo; códigos de saúde em `<details>`.
- [ ] Estados e teste de códigos; commit `feat(web): Bateia composition for sources and status`.

### Task 9: Homologação e Perfil

**Files:** `apps/web/src/routes/HomologationQueuePage.tsx`, `apps/web/src/components/HomologationQueue.tsx`, `apps/web/src/routes/ProfilePage.tsx` e testes.
- [ ] Homologação ganha `PageHeader` e estados; rótulos de ação no verbo da §8 e o mesmo verbo na confirmação.
- [ ] Perfil: rótulos de campos e enums pt-BR (família de cargo, senioridade, modo de trabalho), mensagem de salvo "Perfil salvo. A próxima leitura da Inbox usa esta versão." só se for verdade no código (conferir quando a reavaliação roda; senão, "Perfil salvo.").
- [ ] Estados e teste de códigos; commit `feat(web): Bateia composition for homologation and profile`.

---

## Área C — Backend da Inbox (DESIGN §5 e §8)

### Task 10: Motivo determinístico por vaga

**Files:**
- Modify: `src/opportunity_radar/dashboard/queries.py` (`InboxItem`, `_inbox_statement` ou consulta em lote após a página), `src/opportunity_radar/presentation/http/dashboard.py` (`InboxItemResponse`)
- Test: `tests/backend/dashboard/test_queries.py`, `tests/backend/dashboard/test_inbox_cost_shape.py`, `tests/backend/dashboard/test_tenancy.py`

**Interfaces:**
- Produces: `InboxItem.top_factor_code: str | None = None` e `InboxItemResponse.top_factor_code: str | None = None` (JSON `top_factor_code`, camelCase no cliente pelo mapeamento existente de `apps/web/src/lib/api.ts`).

- [ ] **Step 1: Testes que falham**
  - `test_top_factor_is_known_met_factor_with_highest_contribution`: fatores `TECHNOLOGY_FIT` (KNOWN, raw 0.9, contrib 30), `RECENCY` (KNOWN, raw 1.0, contrib 10), `COMPANY_PRIORITY` (UNKNOWN) → `"TECHNOLOGY_FIT"`.
  - `test_top_factor_ignores_missed_and_unknown`: só fatores KNOWN com raw < 0.5 ou UNKNOWN/NOT_APPLICABLE → `None`.
  - `test_top_factor_tie_breaks_by_factor_code`: contribuições iguais → menor `factor_code` em ordem alfabética.
  - `test_top_factor_uses_current_assessment_only`: avaliação antiga com outro fator vencedor não influencia.
  - `test_top_factor_scoped_to_owner_sub` em `test_tenancy.py`.
  - `test_inbox_cost_shape`: o número de statements da listagem cresce no máximo 1 (consulta em lote por `assessment_id IN (...)`), nunca por item.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/backend/dashboard -k "top_factor or cost_shape or tenancy" -v`.
- [ ] **Step 3: Implementar** com uma consulta em lote sobre `MatchFactorModel` (`DISTINCT ON (assessment_id)` ordenado por `contribution DESC, factor_code ASC`, filtro `status = 'KNOWN' AND raw_score >= 0.5`), aplicada aos `assessment_id` da página.
- [ ] **Step 4: Rodar e ver passar; `ruff check`, `ruff format --check`.**
- [ ] **Step 5: Commit** `feat(api): deterministic top factor per Inbox row`.

### Task 11: Resumo da Inbox (contador e próxima coleta)

**Files:**
- Create: `src/opportunity_radar/dashboard/inbox_summary.py`
- Modify: `src/opportunity_radar/presentation/http/dashboard.py`
- Test: novo `tests/backend/dashboard/test_inbox_summary.py`, `tests/backend/http/` (padrão de integração existente)

**Interfaces:**
- Produces: `GET /dashboard/inbox/summary` (mesmo prefixo de `/inbox`) → `InboxSummaryResponse { worth_count: int, collected_count: int, since: datetime, next_collection_at: datetime | None }`; função `inbox_summary(session, owner_sub: str, *, now: datetime) -> InboxSummary`.

- [ ] **Step 1: Testes que falham**
  - `since` = 00:00 de ontem em `America/Sao_Paulo`, convertido para UTC (now 2026-10-20T03:30Z → since 2026-10-19T03:00Z).
  - `collected_count` = vagas com `first_seen_at >= since` visíveis pelo mesmo filtro padrão da Inbox (área do perfil ativo, `only_recent`), para que o número bata com a lista.
  - `worth_count` = dessas, as com avaliação atual de veredito `HIGH_PRIORITY` ou `RECOMMENDED` do `owner_sub`. **Ruling a confirmar pelo dono.**
  - Avaliação de outro `owner_sub` não conta (Review Focus 4); vaga vista às 01h UTC de ontem (22h de anteontem em SP) não conta (Review Focus 5).
  - `next_collection_at` = menor `next_due_at(...)` futuro entre fontes habilitadas e agendadas, montando `SourceSchedulingState` do mesmo jeito que `worker.py:822`; todas manuais → `None`.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** Reusar `_inbox_filters`/`InboxQuery` para o recorte, sem copiar SQL. Se montar `SourceSchedulingState` exigir mais que extrair uma função de `worker.py`, extrair `load_scheduling_states(session, now)` para `acquisition/scheduling.py` e usá-la nos dois lugares. Sem migration; se a consulta pedir índice novo, parar e reportar antes (migration exige teste em `tests/backend/migrations/`).
- [ ] **Step 4: Rodar e ver passar; ruff.**
- [ ] **Step 5: Commit** `feat(api): Inbox summary with worth count and next collection`.

### Task 12: Inbox consome motivo e resumo (web)

**Files:**
- Create: `apps/web/src/features/matching/factors.ts` (move `factorLabels` de `OpportunityDetailPage.tsx:76`)
- Modify: `apps/web/src/lib/api.ts` (tipos `topFactorCode`, `InboxSummary`), `apps/web/src/routes/InboxPage.tsx`, `apps/web/src/routes/OpportunityDetailPage.tsx`, `DESIGN.md` §5
- Test: `apps/web/src/routes/InboxPage.test.tsx`, `apps/web/src/lib/time.test.ts`

- [ ] **Step 1: Testes que falham**
  - Sem `analysisSummary` e com `topFactorCode: 'TECHNOLOGY_FIT'`: `data-testid="inbox-reason"` diz "Combina em skills da vaga." (rótulo do mapa em minúscula inicial). Com `analysisSummary` o resumo da IA vence. Código sem rótulo no mapa → sem linha de motivo (nunca código cru).
  - Cabeçalho com resumo `{worth: 6, collected: 214}`: "6 vagas valem seu tempo, de 214 coletadas desde ontem."; singular "1 vaga vale seu tempo, de 1 coletada desde ontem."; resumo com erro → cabeçalho cai para o total da lista de T4.
  - Estado vazio com `nextCollectionAt` 09:00Z: "Nada novo desde ontem. A próxima coleta roda às 6h." (hora local de São Paulo via `formatHour`); sem `nextCollectionAt`: só "Nada novo desde ontem."
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** com uma query `['inbox-summary']` separada (não bloqueia a lista). Atualizar DESIGN §5 "Motivo principal": sem resumo da IA, a linha usa o fator atendido de maior peso vindo da API.
- [ ] **Step 4: `npm run check`**, anotar arquivos, testes e gzip.
- [ ] **Step 5: Commit** `feat(web): Inbox reason and daily count from the API`.

---

## Área D — Conferência e entregas do dono

### Task 13: Captura do app real e E2E

**Files:** `docs/54-review/README.md`, `docs/54-review/capture-playwright.cjs`, `docs/54-review/screenshots/`

- [ ] Rodar a captura do app real (claro e escuro; 320, 375, 768, 1024, 1280, 1440px) em todas as rotas, com API mockada como na rodada anterior, e uma segunda passada com Clerk real (chave de desenvolvimento lida pelo Vite, sem abrir o arquivo) se a instância de desenvolvimento estiver disponível; senão registrar "Clerk real não capturado" e o porquê.
- [ ] E2E com Docker: `docker compose -f compose.ci.yaml up --build --abort-on-container-exit` (ou o alvo de E2E do `Makefile`); registrar a saída literal resumida.
- [ ] README: tabela rota × tema × largura, overflow horizontal (esperado 0), contraste, gzip final, o que não foi capturado e por quê (corrige os minors de T8: nomear o build comparado e o erro de health não mockado). Commit `docs(web): final Bateia capture review`.

### Task 14: Checklist do dono (repositório, domínio, handle, INPI)

**Files:** Create `docs/marca-bateia-checklist-dono.md`

- [ ] Para cada item (renomear repo GitHub; comprar getbateia.com e bateiaapp.com.br; criar handle `bateia-app`; busca INPI nas classes 9, 35, 42): o que o dono faz, onde, custo conhecido, e o que muda no código depois, com os arquivos achados por `grep` de `Opportunity-Radar`/`opportunity-radar`/domínio atual (remotes, README, CLAUDE.md, workflows `.github/`, `wrangler.jsonc`, CORS e origens permitidas da API, Clerk allowed origins e redirect URLs, `site.webmanifest`). Deixar explícito que pacote Python e nomes técnicos ficam `opportunity-radar` (DESIGN, topo).
- [ ] Commit `docs: owner checklist for Bateia rename, domain, handle and INPI`.

### Final

- [ ] Revisão da branch inteira com o modelo mais capaz (Opus), diff `origin/main..HEAD`.
- [ ] Uma onda de correção se a revisão pedir; `npm run check` e pytest dos módulos tocados de novo.
- [ ] Listar todas as linhas "Ruling:" do ledger `.superpowers/sdd/2026-10-20-marca-bateia-final/progress.md` e atualizar a memória `branding-checkpoint`.

## Decisões que peço ao dono antes de executar

1. **"Valem seu tempo"** = veredito atual Alta prioridade ou Recomendada. Alternativa: score >= 70.
2. **"Desde ontem"** = desde 00:00 de ontem em São Paulo. Alternativa: últimas 24 horas.
3. **Wordmark** em 1.5rem e ajuste da regra do x-height na §4 (T2).
4. **Branch única** com backend em commits separados, ou backend em `feat/inbox-motivo-api` própria (T12 depende dela).
