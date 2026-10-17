import { createHash } from 'node:crypto'
import { spawn } from 'node:child_process'
import { promises as fs } from 'node:fs'
import http from 'node:http'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const playwrightModule = process.env.UX_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.UX_PLAYWRIGHT_MODULE).href
  : new URL('../../tests/e2e/browser/node_modules/playwright/index.mjs', import.meta.url).href
const { chromium } = await import(playwrightModule)

const root = fileURLToPath(new URL('../..', import.meta.url))
const docs = path.join(root, 'docs/56-regras-ux-trafego')
const output = path.join(docs, 'ux-captures')
const host = '127.0.0.1'
const port = 54156
const origin = `http://${host}:${port}`
const vite = process.env.UX_VITE_MODULE ?? path.join(root, 'apps/web/node_modules/vite/bin/vite.js')
const failures = []
const blockedRequests = []
const screenshots = []
const focusChecks = []
const targetChecks = []
let contrastEvidence
let readyStatus = 'pending'
let readyError = ''
const fail = (message) => failures.push(message)

const opportunity = {
  id: 'ux-opportunity', fingerprint: 'fixture-fingerprint', fingerprint_version: 'v1',
  title: 'Engenheira de Plataforma', company_id: 'company-fixture', company_name: 'Empresa demonstrativa',
  location: 'São Paulo', work_mode: 'HYBRID', seniority: 'SENIOR', contract_type: 'FULL_TIME',
  description: 'Conteúdo de demonstração. Dados fictícios para revisão visual.', lifecycle_status: 'ACTIVE',
  published_at: '2026-10-10T12:00:00Z', recency_effective_date: '2026-10-10T12:00:00Z',
  recency_basis: 'published', created_at: '2026-10-10T12:00:00Z', version: 1,
  compensations: [], skills: [], occurrences: [], normalization_results: [], sibling_locations: [], relevance_mark: null,
}
const item = {
  opportunity_id: opportunity.id, title: opportunity.title, company_id: opportunity.company_id,
  company_name: opportunity.company_name, company_priority: null, location: opportunity.location,
  work_mode: 'HYBRID', seniority: 'SENIOR', contract_type: 'FULL_TIME', lifecycle_status: 'ACTIVE',
  role_family: 'SOFTWARE_ENGINEERING', published_at: '2026-10-10T12:00:00Z',
  recency_effective_date: '2026-10-10T12:00:00Z', recency_basis: 'published', date_is_estimated: false,
  opportunity_version: 1, assessment_id: 'assessment-fixture', assessment_opportunity_version: 1,
  assessment_profile_version_id: 'profile-fixture', current_profile_version_id: 'profile-fixture',
  verdict: 'RECOMMENDED', eligibility: 'ELIGIBLE', score: '82', confidence: '0.7', rules_version: 'fixture-rules',
  is_stale: false, assessed_at: '2026-10-15T12:00:00Z', analysis_status: null,
  analysis_recommended_review: null, analysis_summary: null, applied: false, application_id: null,
  application_stage: null, application_next_action_at: null, has_pending_duplicate: false,
  startup_strength: null, startup_batch: null, sibling_count: 0,
}
const assessment = {
  id: 'assessment-fixture', opportunity_id: opportunity.id, opportunity_version: 1,
  profile_version_id: 'profile-fixture', input_hash: 'a'.repeat(64), rules_version: 'fixture-rules',
  taxonomy_version: 'fixture-taxonomy', eligibility: 'ELIGIBLE', eligibility_details: [],
  status: 'COMPLETED', verdict: 'RECOMMENDED', score: '82', confidence: '0.7',
  assessed_at: '2026-10-15T12:00:00Z', created_at: '2026-10-15T12:00:00Z', factors: [], analysis: null,
}
const savedSearch = {
  id: 'saved-fixture', name: 'Plataforma híbrida', term: 'plataforma', filters: { work_mode: 'HYBRID' },
  last_opened_at: null, created_at: '2026-10-01T00:00:00Z', new_count: 2,
}
const overview = {
  opportunities_total: 18, opportunities_active: 12, new_opportunities: 3,
  new_opportunity_window_days: 7, assessed_opportunities: 8,
  verdict_counts: { RECOMMENDED: 4, HIGH_PRIORITY: 1 }, analyses_degraded: 0,
  sources_total: 4, sources_enabled: 3, sources_failing: 0, failing_sources: [],
  pending_normalizations: 0, applications_active: 2, applications_by_stage: { INTERVIEW: 1 },
  follow_ups_due: 1, follow_up_window_days: 7, precision_percent: null,
  precision_marked_count: 0, companies_covered: 4, companies_with_ats: 2,
}
const application = {
  id: 'application-fixture', opportunity_id: opportunity.id, opportunity_title: opportunity.title,
  company_name: opportunity.company_name, profile_version_id: 'profile-fixture', current_stage: 'INTERVIEW',
  status: 'ACTIVE', outcome: null, next_action: null, next_action_at: null, notes: null,
  applied_at: null, started_at: '2026-10-10T12:00:00Z', closed_at: null, version: 1,
  allowed_transitions: [], history: [],
}

async function portBusy() {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port })
    socket.once('connect', () => { socket.destroy(); resolve(true) })
    socket.once('error', () => resolve(false))
  })
}

async function ready() {
  return new Promise((resolve) => {
    const request = http.get(`${origin}/docs/56-regras-ux-trafego/ux-fixture.html`, (response) => {
      response.resume()
      readyStatus = String(response.statusCode)
      resolve(response.statusCode === 200)
    })
    request.once('error', (error) => { readyError = error.message; resolve(false) })
    request.setTimeout(700, () => { request.destroy(); resolve(false) })
  })
}

async function startServer() {
  if (await portBusy()) throw new Error(`Port ${port} is in use; refusing to use an unknown server.`)
  const child = spawn(process.execPath, [vite, '--config', 'docs/56-regras-ux-trafego/vite.ux.config.ts', '--configLoader', process.env.UX_CONFIG_LOADER ?? 'runner', '--host', host, '--strictPort', '--port', String(port)], {
    cwd: root, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true,
  })
  let stderr = ''
  child.stdout.on('data', (chunk) => { stderr += chunk })
  child.stderr.on('data', (chunk) => { stderr += chunk })
  const deadline = Date.now() + 15000
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Fixture Vite stopped: ${stderr.trim()}`)
    if (await ready()) return child
    await new Promise((resolve) => setTimeout(resolve, 150))
  }
  child.kill()
  throw new Error(`Fixture Vite did not serve readiness URL (HTTP ${readyStatus}; ${readyError}): ${stderr.trim()}`)
}

async function git(args) {
  return new Promise((resolve, reject) => {
    const child = spawn('git', args, { cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
    let stdout = ''; let stderr = ''
    child.stdout.on('data', (chunk) => { stdout += chunk })
    child.stderr.on('data', (chunk) => { stderr += chunk })
    child.once('exit', (code) => code === 0 ? resolve(stdout.trim()) : reject(new Error(stderr)))
  })
}

async function workspaceEvidence() {
  const head = await git(['rev-parse', 'HEAD'])
  const status = await git(['status', '--porcelain=v1'])
  const trackedDiff = await git(['diff', '--binary', 'HEAD'])
  const untracked = await git(['ls-files', '--others', '--exclude-standard'])
  const hash = createHash('sha256').update(trackedDiff)
  const generatedPrefixes = ['docs/56-regras-ux-trafego/ux-captures/', 'docs/56-regras-ux-trafego/artifacts/', 'docs/56-regras-ux-trafego/.tmp/', 'apps/web/.tmp/', '.validation/', '.worktrees/']
  for (const file of untracked.split('\n').filter(Boolean).sort()) {
    if (generatedPrefixes.some((prefix) => file.replaceAll('\\', '/').startsWith(prefix))) continue
    hash.update(file).update(await fs.readFile(path.join(root, file)))
  }
  return { head, dirty: status.length > 0, status, workingTreeSha256: hash.digest('hex'), hashExcludes: generatedPrefixes }
}

function fixtureResponse(url, state, route) {
  const pathname = url.pathname
  const isTarget = (pathname === '/inbox' && route === 'inbox') ||
    (pathname.startsWith('/opportunities/') && route === 'detail') ||
    (pathname.startsWith('/matches') && route === 'detail') ||
    (pathname.startsWith('/applications') && route === 'pipeline') ||
    (pathname === '/overview' && route === 'overview')
  if (state === 'loading' && isTarget) return null
  if (state === 'error' && isTarget) return { status: 503, body: { detail: 'Fixture offline error' } }
  if (pathname === '/session') return { body: { is_owner: true } }
  if (/^\/saved-searches\/[^/]+\/new-count$/.test(pathname)) return { body: { new_count: 2 } }
  if (pathname === '/inbox') {
    const items = state === 'empty' ? [] : [{ ...item, is_stale: state === 'stale' }]
    return { body: { items, total: items.length, offset: 0, limit: 25, order: 'priority', off_filter_count: 0 } }
  }
  if (pathname === '/saved-searches/summary') return { body: [savedSearch] }
  if (pathname === '/saved-searches') return { body: [{ ...savedSearch, new_count: undefined }] }
  if (pathname.endsWith('/duplicate-candidates')) return { body: { items: [] } }
  if (pathname.startsWith('/opportunities/')) return { body: opportunity }
  if (pathname.startsWith('/matches')) return { body: { items: state === 'empty' ? [] : [{ ...assessment, is_stale: state === 'stale' }] } }
  if (pathname.startsWith('/duplicate-candidates')) return { body: { items: [] } }
  if (pathname.startsWith('/applications')) {
    const items = state === 'empty' ? [] : [application]
    return { body: { items, total: items.length, offset: 0, limit: 12 } }
  }
  if (pathname === '/overview') return { body: overview }
  if (pathname === '/analysis-metrics') return { body: { generated_at: '', current_model: '', pending: 0, windows: [], ai: { state: 'disabled', window_hours: 24, by_model: [], cache_hit_rate: null } } }
  if (pathname === '/source-metrics') return { body: { generated_at: '', windows: [{ window: '24h', since: '', until: '', sources: [] }, { window: '7d', since: '', until: '', sources: [] }] } }
  return undefined
}

async function main() {
  await fs.mkdir(output, { recursive: true })
  const server = await startServer()
  let browser
  try {
    browser = await chromium.launch({ headless: true })
    const cases = [
      ...['inbox', 'detail', 'pipeline', 'overview'].flatMap((route) =>
        [['1440', 1440], ['768', 768], ['360', 360]].map(([label, width]) => ({ route, state: 'loaded', label, width }))),
      { route: 'inbox', state: 'error', label: 'state-error', width: 1440 },
      { route: 'detail', state: 'stale', label: 'state-stale', width: 1440 },
      { route: 'pipeline', state: 'empty', label: 'state-empty', width: 1440 },
      { route: 'overview', state: 'loading', label: 'state-loading', width: 1440 },
    ]
    for (const itemCase of cases) {
      const context = await browser.newContext({ viewport: { width: itemCase.width, height: 1050 } })
      await context.route('**/*', async (route) => {
        const requestUrl = new URL(route.request().url())
        if (requestUrl.origin !== origin) {
          blockedRequests.push(requestUrl.href)
          fail(`External request blocked: ${requestUrl.href}`)
          return route.abort()
        }
        if (requestUrl.pathname.startsWith('/api/')) {
          const mock = fixtureResponse(new URL(requestUrl.pathname.slice(4) + requestUrl.search, 'http://fixture'), itemCase.state, itemCase.route)
          if (mock === null) return
          if (mock === undefined) {
            fail(`Unregistered API request: ${requestUrl.pathname}`)
            return route.abort()
          }
          return route.fulfill({ status: mock.status ?? 200, contentType: 'application/json', body: JSON.stringify(mock.body) })
        }
        return route.continue()
      })
      const page = await context.newPage()
      page.on('pageerror', (error) => fail(`Browser error (${itemCase.route}/${itemCase.state}): ${error.message}`))
      const response = await page.goto(`${origin}/docs/56-regras-ux-trafego/ux-fixture.html?route=${itemCase.route}&state=${itemCase.state}`, { waitUntil: 'domcontentloaded' })
      if (response?.status() !== 200) fail(`Fixture page did not load (${itemCase.route}/${itemCase.state}): HTTP ${response?.status() ?? 'no response'}`)
      try {
        if (itemCase.state === 'loading') await page.waitForTimeout(250)
        else if (itemCase.state === 'error') await page.getByRole('alert').first().waitFor({ timeout: 8000 })
        else if (itemCase.state === 'stale') await page.getByText('Esta decisão foi calculada com dados anteriores.', { exact: false }).waitFor({ timeout: 8000 })
        else if (itemCase.state === 'empty') await page.getByText('Nenhuma candidatura em andamento.', { exact: false }).waitFor({ timeout: 8000 })
        else {
        const readySelectors = {
          inbox: 'main a[href*="/opportunities/"]',
          detail: 'main #decisao',
          pipeline: 'main a[href*="/opportunities/"]',
          overview: 'main h1',
        }
          await page.locator(readySelectors[itemCase.route]).first().waitFor({ timeout: 8000 })
          if (itemCase.route === 'detail') {
            await page.getByText('Filtros eliminatórios', { exact: true }).waitFor({ timeout: 8000 })
          }
          if (itemCase.route === 'overview') {
            await page.getByText('Plataforma híbrida', { exact: true }).waitFor({ timeout: 8000 })
          }
          if (await page.getByRole('alert').count()) fail(`Unexpected alert on loaded ${itemCase.route}: ${(await page.getByRole('alert').allInnerTexts()).join(' | ')}`)
        }
      } catch (error) {
        fail(`Readiness failed for ${itemCase.route}/${itemCase.state}: ${error instanceof Error ? error.message : String(error)}`)
      }
      if (!contrastEvidence) {
        contrastEvidence = await page.evaluate(() => {
          const root = getComputedStyle(document.documentElement)
          const color = (token) => root.getPropertyValue(`--color-${token}`).trim()
          const luminance = (hex) => {
            const channels = hex.replace('#', '').match(/.{2}/g).map((part) => Number.parseInt(part, 16) / 255)
            const linear = channels.map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
          }
          const ratio = (foreground, background) => {
            const values = [luminance(color(foreground)), luminance(color(background))].sort((a, b) => b - a)
            return Number(((values[0] + 0.05) / (values[1] + 0.05)).toFixed(2))
          }
          return [
            { pair: 'ink/canvas (page title/body)', foreground: 'ink', background: 'canvas', ratio: ratio('ink', 'canvas'), minimum: 4.5 },
            { pair: 'subtle/canvas (secondary text)', foreground: 'subtle', background: 'canvas', ratio: ratio('subtle', 'canvas'), minimum: 4.5 },
            { pair: 'muted/surface (metadata)', foreground: 'muted', background: 'surface', ratio: ratio('muted', 'surface'), minimum: 4.5 },
            { pair: 'danger-ink/danger-surface', foreground: 'danger-ink', background: 'danger-surface', ratio: ratio('danger-ink', 'danger-surface'), minimum: 4.5 },
            { pair: 'warning-ink/warning-surface', foreground: 'warning-ink', background: 'warning-surface', ratio: ratio('warning-ink', 'warning-surface'), minimum: 4.5 },
            { pair: 'surface/accent (primary button)', foreground: 'surface', background: 'accent', ratio: ratio('surface', 'accent'), minimum: 4.5 },
          ]
        })
        for (const pair of contrastEvidence) if (pair.ratio < pair.minimum) fail(`Nominal contrast below ${pair.minimum}:1 for ${pair.pair} (${pair.ratio}:1).`)
      }
      if (itemCase.state === 'loading' && !(await page.getByRole('status').count())) fail('Loading scenario did not render a pending state.')
      if (itemCase.state === 'stale' && !(await page.getByRole('status').filter({ hasText: 'dados anteriores' }).count())) fail('Stale scenario did not identify the prior assessment.')
      const dims = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }))
      if (dims.scrollWidth > dims.clientWidth) fail(`Horizontal overflow ${itemCase.route}/${itemCase.label}: ${dims.scrollWidth}>${dims.clientWidth}`)
      if (itemCase.route === 'inbox' && itemCase.label === '1440') {
        await page.keyboard.press('Tab')
        if (!(await page.locator(':focus').first().innerText()).includes('Pular para o conteúdo')) fail('Keyboard first focus target is not the skip link.')
        const focusEvidence = []
        for (let index = 0; index < 8; index += 1) {
          if (await page.locator('vite-error-overlay').count()) {
            fail(`Vite runtime error overlay prevents keyboard inspection on ${itemCase.route}.`)
            break
          }
          const focused = page.locator(':focus').first()
          if (!(await focused.count())) {
            fail(`No keyboard focus target at stop ${index + 1}.`)
            break
          }
          const focus = await focused.evaluate((element) => {
            const style = getComputedStyle(element)
            return { label: (element.innerText || element.getAttribute('aria-label') || element.getAttribute('placeholder') || element.tagName).trim(), outlineWidth: style.outlineWidth, outlineStyle: style.outlineStyle }
          })
          focusEvidence.push(focus)
          if (focus.outlineStyle === 'none' || Number.parseFloat(focus.outlineWidth) < 3) fail(`Keyboard focus indicator is below 3px at stop ${index + 1}: ${JSON.stringify(focus)}`)
          await page.keyboard.press('Tab')
        }
        focusChecks.push({ route: itemCase.route, viewport: itemCase.width, stops: focusEvidence })
      }
      if (itemCase.state === 'loaded' && itemCase.width < 768) {
        const targets = await page.locator('main button:visible, main input:visible, main select:visible, main textarea:visible, main a:visible').evaluateAll((elements) =>
          elements.map((element) => {
            const rect = element.getBoundingClientRect()
            return { label: (element.innerText || element.getAttribute('aria-label') || element.getAttribute('placeholder') || '').trim(), width: rect.width, height: rect.height, prose: Boolean(element.closest('[data-testid="opportunity-description"]')) }
          }).filter((target) => !target.prose && (target.width < 44 || target.height < 44)),
        )
        targetChecks.push({ route: itemCase.route, viewport: itemCase.width, tooSmall: targets })
        if (targets.length) fail(`${itemCase.route} ${itemCase.width}px has interactive targets below 44px: ${JSON.stringify(targets)}`)
      }
      const file = path.join(output, `${itemCase.route}-${itemCase.label}.png`)
      await page.screenshot({ path: file, fullPage: true })
      screenshots.push(path.relative(root, file))
      await context.close()
    }
    const evidence = {
      generatedAt: new Date().toISOString(),
      workspace: await workspaceEvidence(),
      screenshots,
      focusChecks,
      targetChecks,
      contrastEvidence,
      blockedRequests,
      failures,
      limits: [
        'Components are mounted directly with a test-only Clerk identity shim; this is not an authentication test.',
        'All API responses are deterministic local fixtures and do not prove backend data or runtime freshness.',
        'Screenshots are visual review evidence only; they do not establish WCAG conformance or production readiness.',
      ],
    }
    await fs.writeFile(path.join(output, 'report.json'), `${JSON.stringify(evidence, null, 2)}\n`)
    if (failures.length) throw new Error(`Visual fixture reported ${failures.length} failures; see ${path.join(output, 'report.json')}`)
  } finally {
    await browser?.close()
    server.kill()
  }
}

main().catch((error) => { console.error(error); process.exitCode = 1 })
