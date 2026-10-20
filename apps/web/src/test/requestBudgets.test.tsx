import { afterAll, afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { createHash } from 'node:crypto'
import { QueryClientProvider, onlineManager, useMutation, useQueries, useQuery } from '@tanstack/react-query'
import { act, type ReactElement, useEffect, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import { installTestAuth } from './auth'
import * as api from '../lib/api'
import { NetworkError } from '../lib/api'
import {
  createRequestMetricsFetch,
  createScenarioQueryClient,
  normalizedEndpoint,
  requestMetricsMode,
  type RequestMetricsReport,
} from './requestMetrics'
import { render } from '../components/testing'
import { SavedSearchesWithNews } from '../routes/OverviewPage'
import { OverviewPage } from '../routes/OverviewPage'
import { InboxPage } from '../routes/InboxPage'
import { OpportunityDetailPage } from '../routes/OpportunityDetailPage'
import { Route, Routes } from 'react-router-dom'
import { PipelinePage } from '../routes/PipelinePage'
import { useInbox } from '../features/dashboard/useInbox'
import { useEvaluateOpportunity, useLatestAssessment } from '../features/matching/useAssessment'
import { useOpportunityApplication, useStartApplication } from '../features/pipeline/usePipeline'
import { useConfirmDuplicate, useMarkRelevance, useOpportunity } from '../features/opportunities/useOpportunity'
import { useSaveProfile } from '../features/profile/useProfile'
import { useManualIntake } from '../features/sources/useSources'

installTestAuth()

const { privateFetch } = api
const apiWithFailure = api as typeof api & {
  failureFrom?: (response: Response, method?: string) => Promise<Error>
}

const reports: Array<{ scenario: string, report: RequestMetricsReport }> = []
const evaluationCalls = { inbox: 0, overview: 0, summary: 0 }
const mutationInvalidationCalls = new Map<string, number>()

function remember(scenario: string, report: RequestMetricsReport) {
  reports.push({ scenario, report })
  return report
}

function applicationSourceFiles(directory = 'src'): string[] {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const file = join(directory, entry.name)
      return entry.isDirectory() ? applicationSourceFiles(file) : [file]
    })
    .filter((file) => statSync(file).isFile())
}

afterEach(() => {
  onlineManager.setOnline(true)
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

afterAll(() => {
  const output = process.env.REQUEST_METRICS_OUTPUT
  if (!output) return

  const sourceFiles = [
    ...applicationSourceFiles(),
    'package-lock.json',
    'vite.config.ts',
    'tsconfig.app.json',
    'eslint.config.js',
  ].sort()
  const digest = createHash('sha256')
  for (const file of sourceFiles) digest.update(file).update('\0').update(readFileSync(file))
  const sourceDigest = digest.digest('hex')
  const harness = { sourceFiles, sha256: sourceDigest }
  writeFileSync(output, JSON.stringify({ version: 1, synthetic: true, harness, reports }, null, 2), 'utf8')
  writeFileSync(output.replace(/\.json$/i, '.manifest.json'), JSON.stringify({
    version: 1,
    synthetic: true,
    harness,
    scenarios: reports.map(({ scenario }) => scenario),
  }, null, 2), 'utf8')
})

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

function renderMount(element: ReactElement) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => root.render(element))
  return {
    unmount() {
      act(() => root.unmount())
      container.remove()
    },
  }
}

function EvaluationInvalidationProbe({
  onReady,
}: {
  onReady: (run: () => Promise<unknown>) => void
}) {
  const inbox = useQuery({
    queryKey: ['inbox'],
    queryFn: async () => ++evaluationCalls.inbox,
    staleTime: Infinity,
  })
  const overview = useQuery({
    queryKey: ['overview'],
    queryFn: async () => ++evaluationCalls.overview,
    staleTime: Infinity,
  })
  const summary = useQuery({
    queryKey: ['saved-searches', 'summary'],
    queryFn: async () => ++evaluationCalls.summary,
    staleTime: Infinity,
  })
  const evaluation = useEvaluateOpportunity('opportunity-1')

  useEffect(() => {
    if (inbox.isSuccess && overview.isSuccess && summary.isSuccess) {
      onReady(() => evaluation.mutateAsync())
    }
  }, [evaluation, inbox.isSuccess, onReady, overview.isSuccess, summary.isSuccess])

  return null
}

function savedSearches(total: number) {
  return Array.from({ length: total }, (_, index) => ({
    id: `saved-${index + 1}`,
    name: `Busca ${index + 1}`,
    term: null,
    filters: {},
    last_opened_at: null,
    created_at: '2040-01-01T00:00:00Z',
  }))
}

async function renderSavedSearchScenario(total: number) {
  const mode = requestMetricsMode()
  const metrics = createRequestMetricsFetch(async (request) => {
    const path = new URL(request.url).pathname
    if (path === '/api/saved-searches') return new Response(JSON.stringify(savedSearches(total)))
    if (path === '/api/saved-searches/summary') {
      return new Response(JSON.stringify(savedSearches(total).map((savedSearch) => ({ ...savedSearch, new_count: 0 }))))
    }
    if (/^\/api\/saved-searches\/saved-\d+\/new-count$/.test(path)) {
      return new Response(JSON.stringify({ new_count: 0 }))
    }
    throw new Error(`Unregistered offline fixture: ${request.method} ${path}`)
  })
  vi.stubGlobal('fetch', metrics.fetch)
  const client = createScenarioQueryClient(mode)
  const mount = renderMount(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SavedSearchesWithNews />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  // Legacy mode starts one hook per row after the list response commits. Give React
  // each row a task turn; this keeps the baseline measurement deterministic.
  for (let index = 0; index <= total + 4; index += 1) {
    await flush()
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
  }
  mount.unmount()
  return metrics.report()
}

function applicationFixture() {
  return {
    id: 'application-1',
    opportunity_id: 'opportunity-1',
    opportunity_title: 'Vaga de teste',
    company_name: 'Empresa de teste',
    profile_version_id: 'profile-1',
    current_stage: 'INTERVIEW',
    status: 'ACTIVE',
    outcome: null,
    next_action: null,
    next_action_at: null,
    notes: null,
    applied_at: null,
    started_at: '2040-01-01T00:00:00Z',
    closed_at: null,
    version: 1,
    allowed_transitions: [],
    history: [],
  }
}

function inboxFixture() {
  return {
    opportunity_id: 'opportunity-1', title: 'Vaga de teste', company_id: null, company_name: 'Empresa de teste',
    company_priority: null, location: 'Remote', work_mode: 'REMOTE', seniority: 'SENIOR',
    contract_type: 'FULL_TIME', lifecycle_status: 'ACTIVE', role_family: 'SOFTWARE_ENGINEERING',
    published_at: '2040-01-01T00:00:00Z', recency_effective_date: '2040-01-01T00:00:00Z',
    date_is_estimated: false, opportunity_version: 1, assessment_id: null,
    assessment_opportunity_version: null, assessment_profile_version_id: null,
    current_profile_version_id: null, verdict: null, eligibility: null, score: null, confidence: null,
    rules_version: null, is_stale: null, assessed_at: null, analysis_status: null,
    analysis_recommended_review: null, analysis_summary: null, applied: false, application_id: null,
    application_stage: null, application_next_action_at: null, has_pending_duplicate: false,
    startup_strength: null, startup_batch: null,
  }
}

function opportunityFixture() {
  return {
    id: 'opportunity-1', fingerprint: 'fixture', fingerprint_version: 'fixture', title: 'Vaga de teste',
    company_id: null, company_name: 'Empresa de teste', location: 'Remote', work_mode: 'REMOTE',
    seniority: 'SENIOR', contract_type: 'FULL_TIME', description: null, lifecycle_status: 'ACTIVE',
    published_at: null, created_at: '2040-01-01T00:00:00Z', version: 1, compensations: [], skills: [],
    occurrences: [], normalization_results: [], relevance_mark: null,
  }
}

function overviewFixture() {
  return { opportunities_total: 0, opportunities_active: 0, new_opportunities: 0, new_opportunity_window_days: 7,
    assessed_opportunities: 0, verdict_counts: {}, analyses_degraded: 0, sources_total: 0, sources_enabled: 0,
    sources_failing: 0, failing_sources: [], pending_normalizations: 0, applications_active: 0,
    applications_by_stage: {}, follow_ups_due: 0, follow_up_window_days: 7, precision_percent: null,
    precision_marked_count: 0, companies_covered: 0, companies_with_ats: 0 }
}

function completePageMetrics(savedTotal = 0) {
  return createRequestMetricsFetch(async (request) => {
    const path = new URL(request.url).pathname
    if (path === '/api/overview') return new Response(JSON.stringify(overviewFixture()))
    if (path === '/api/profile') return new Response(JSON.stringify({ id: 'profile-1', number: 1, status: 'ACTIVE', profile_lock_version: 1, skills: [], experiences: [], projects: [], preferences: {} }))
    if (path === '/api/analysis-metrics') return new Response(JSON.stringify({ generated_at: '2040-01-01T00:00:00Z', current_model: '', pending: 0, windows: [], ai: { state: 'disabled', window_hours: 24, by_model: [], cache_hit_rate: null } }))
    if (path === '/api/ai-budget') return new Response(JSON.stringify({
      state: 'disabled',
      day: '2026-10-18',
      resets_at: '2026-10-19T00:00:00Z',
      interactive_reserve_requests: 0,
      models: [],
    }))
    if (path === '/api/source-metrics') return new Response(JSON.stringify({ generated_at: '2040-01-01T00:00:00Z', windows: [] }))
    if (path === '/api/saved-searches/summary') return new Response(JSON.stringify(savedSearches(savedTotal).map((item) => ({ ...item, new_count: 0 }))))
    if (path === '/api/saved-searches') return new Response(JSON.stringify(savedSearches(savedTotal)))
    if (/^\/api\/saved-searches\/saved-\d+\/new-count$/.test(path)) return new Response(JSON.stringify({ new_count: 0 }))
    if (path === '/api/inbox/summary') return new Response(JSON.stringify({ worth_count: 1, collected_count: 1, since: '2039-12-31T03:00:00Z', next_collection_at: null, generated_at: '2040-01-01T00:00:00Z' }))
    if (path === '/api/inbox') return new Response(JSON.stringify({ items: [inboxFixture()], total: 1, offset: 0, limit: 25, off_filter_count: 0 }))
    if (path === '/api/opportunities/opportunity-1') return new Response(JSON.stringify(opportunityFixture()))
    if (path === '/api/matches') return new Response(JSON.stringify({ items: [] }))
    if (path === '/api/applications') return new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 12 }))
    if (path === '/api/opportunities/opportunity-1/duplicate-candidates') return new Response(JSON.stringify({ items: [] }))
    throw new Error(`Unregistered offline fixture: ${request.method} ${path}`)
  })
}

function InboxProbe({ search }: { search?: string }) {
  useInbox({ page: 1, pageSize: 25, order: 'priority', search })
  return null
}

function AssessmentProbe() {
  useLatestAssessment('opportunity-1')
  return null
}

function OpportunityApplicationProbe() {
  useOpportunityApplication('opportunity-1')
  return null
}

function RelevanceMutationProbe({ onReady }: { onReady: (submit: () => Promise<unknown>) => void }) {
  useOpportunity('opportunity-1')
  const mutation = useMarkRelevance('opportunity-1')
  useEffect(() => onReady(() => mutation.mutateAsync({ relevant: true })), [mutation, onReady])
  return null
}

function MutationInvalidationProbe<TInput>({
  activeRoutes,
  input,
  useMutationHook,
  onReady,
}: {
  activeRoutes: readonly { queryKey: readonly string[], endpoint: string }[]
  input: TInput
  useMutationHook: () => { mutateAsync: (value: TInput) => Promise<unknown> }
  onReady: (run: () => Promise<unknown>) => void
}) {
  const ready = useRef(false)
  const queries = useQueries({
    queries: activeRoutes.map(({ queryKey, endpoint }) => ({
      queryKey,
      queryFn: async () => {
        const key = JSON.stringify(queryKey)
        mutationInvalidationCalls.set(key, (mutationInvalidationCalls.get(key) ?? 0) + 1)
        const response = await privateFetch(`/api${endpoint}`)
        if (!response.ok) throw new Error(`Fixture GET failed: ${endpoint}`)
        return response.json() as Promise<{ version: number }>
      },
      staleTime: Infinity,
    })),
  })
  const mutation = useMutationHook()

  useEffect(() => {
    if (!ready.current && queries.every((query) => query.isSuccess)) {
      ready.current = true
      onReady(() => mutation.mutateAsync(input))
    }
  }, [input, mutation, onReady, queries])

  return null
}

function activeInvalidationCounts(activeRoutes: readonly { queryKey: readonly string[] }[]) {
  return Object.fromEntries(activeRoutes.map(({ queryKey }) => [JSON.stringify(queryKey), mutationInvalidationCalls.get(JSON.stringify(queryKey))]))
}

async function runMutationInvalidation<TInput>({
  activeRoutes,
  input,
  useMutationHook,
}: {
  activeRoutes: readonly { queryKey: readonly string[], endpoint: string }[]
  input: TInput
  useMutationHook: () => { mutateAsync: (value: TInput) => Promise<unknown> }
}) {
  mutationInvalidationCalls.clear()
  let run: (() => Promise<unknown>) | null = null
  const client = createScenarioQueryClient('final')
  const mount = renderMount(
    <QueryClientProvider client={client}>
      <MutationInvalidationProbe activeRoutes={activeRoutes} input={input} useMutationHook={useMutationHook} onReady={(next) => { run = next }} />
    </QueryClientProvider>,
  )
  for (let index = 0; index < 8 && run === null; index += 1) {
    await flush()
    await new Promise<void>((resolve) => setTimeout(resolve, 0))
  }
  expect(run).not.toBeNull()
  await act(async () => { await (run as () => Promise<unknown>)() })
  await flush()
  mount.unmount()
  expect(activeInvalidationCounts(activeRoutes)).toEqual(
    Object.fromEntries(activeRoutes.map(({ queryKey }) => [JSON.stringify(queryKey), 2])),
  )
  expect(activeRoutes.map(({ queryKey }) => client.getQueryData(queryKey))).toEqual(activeRoutes.map(() => ({ version: 2 })))
}

function NonRetryQueryProbe({ endpoint, parserFailure = false }: { endpoint: string, parserFailure?: boolean }) {
  useQuery({
    queryKey: ['non-retry-probe', endpoint],
    queryFn: async () => {
      const response = await privateFetch(`/api/${endpoint}`)
      if (!response.ok) throw await (apiWithFailure.failureFrom?.(response) ?? Promise.resolve(new Error('HTTP failure')))
      if (parserFailure) throw new SyntaxError('fixture parser failure')
      return response.json()
    },
  })
  return null
}

function NonRetryMutationProbe({ onReady }: { onReady: (run: () => Promise<unknown>) => void }) {
  const mutation = useMutation({
    mutationFn: async () => {
      const response = await privateFetch('/api/write-failure', { method: 'POST' })
      if (!response.ok) throw await (apiWithFailure.failureFrom?.(response, 'POST') ?? Promise.resolve(new Error('HTTP failure')))
      return response.json()
    },
  })
  useEffect(() => onReady(() => mutation.mutateAsync()), [mutation, onReady])
  return null
}

function createHookMetrics() {
  return createRequestMetricsFetch(async (request) => {
    const url = new URL(request.url)
    if (url.pathname === '/api/inbox') {
      return new Response(JSON.stringify({ items: [inboxFixture()], total: 1, offset: 0, limit: 25, off_filter_count: 0 }))
    }
    if (url.pathname === '/api/matches') return new Response(JSON.stringify({ items: [] }))
    if (url.pathname === '/api/applications') {
      return new Response(JSON.stringify({ items: [applicationFixture()], total: 1, offset: 0, limit: 100 }))
    }
    if (url.pathname === '/api/opportunities/opportunity-1' && request.method === 'GET') {
      return new Response(JSON.stringify(opportunityFixture()))
    }
    if (url.pathname === '/api/opportunities/opportunity-1/relevance' && request.method === 'POST') {
      return new Response(JSON.stringify({
        id: 'relevance-1', relevant: true, reason: null, note: null, marked_at: '2040-01-01T00:00:00Z',
      }))
    }
    throw new Error(`Unregistered offline fixture: ${request.method} ${url.pathname}`)
  })
}

async function renderPipelineScenario() {
  const metrics = createRequestMetricsFetch(async (request) => {
    const url = new URL(request.url)
    if (
      url.pathname === '/api/applications' &&
      ['ACTIVE', 'CLOSED'].includes(url.searchParams.get('application_status') ?? '')
    ) {
      return new Response(JSON.stringify({ items: [applicationFixture()], total: 1, offset: 0, limit: 12 }))
    }
    throw new Error(`Unregistered offline fixture: ${request.method} ${url.pathname}`)
  })
  vi.stubGlobal('fetch', metrics.fetch)
  const client = createScenarioQueryClient(requestMetricsMode())
  const mount = renderMount(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PipelinePage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await flush()
  await flush()
  mount.unmount()
  return metrics.report()
}

describe('request metrics harness', () => {
  it.each([0, 5, 20])('measures the real saved-search route component with %s saved searches', async (total) => {
    const report = remember(`saved-searches-${total}`, await renderSavedSearchScenario(total))
    const expectedRequests = report.mode === 'baseline' ? 1 + total : 1
    expect(report.requests).toHaveLength(expectedRequests)
    expect(report.requests[0]).toEqual(
      expect.objectContaining({
        method: 'GET',
        endpoint: report.mode === 'baseline' ? '/saved-searches' : '/saved-searches/summary',
        outcome: 'success',
        trafficKind: 'product',
      }),
    )
    expect(report.requests.filter((entry) => entry.endpoint === '/saved-searches/:id/new-count')).toHaveLength(
      report.mode === 'baseline' ? total : 0,
    )
  })

  it('measures the active Pipeline page without mounting the closed-tab query', async () => {
    const report = remember('pipeline-active', await renderPipelineScenario())
    expect(report.requests).toHaveLength(report.mode === 'baseline' ? 2 : 1)
    expect(report.requests[0]).toEqual(
      expect.objectContaining({ method: 'GET', endpoint: '/applications', outcome: 'success', trafficKind: 'product' }),
    )
    expect(report.requests.map((entry) => entry.endpoint)).toEqual(
      report.mode === 'baseline' ? ['/applications', '/applications'] : ['/applications'],
    )
  })

  it.each([0, 5, 20])('measures a fresh complete Overview cold start with %s saved searches', async (savedTotal) => {
    const metrics = completePageMetrics(savedTotal)
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient(requestMetricsMode())
    const mount = renderMount(
      <QueryClientProvider client={client}>
        <MemoryRouter><OverviewPage /></MemoryRouter>
      </QueryClientProvider>,
    )
    for (let index = 0; index < 8; index += 1) {
      await flush()
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
    }
    mount.unmount()
    const report = remember(`cold-overview-${savedTotal}`, metrics.report())
    expect(report.requests).toHaveLength(requestMetricsMode() === 'baseline' ? 5 + savedTotal : 6)
    expect(report.requests.every((entry) => entry.outcome === 'success')).toBe(true)
  })

  it.each([
    ['Inbox', <InboxPage />, 4],
    ['Detail', <Routes><Route path="/opportunities/:opportunityId" element={<OpportunityDetailPage />} /></Routes>, 4],
  ])('measures a fresh complete %s cold start', async (name, page, expectedRequests) => {
    const metrics = completePageMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    const mount = renderMount(<QueryClientProvider client={createScenarioQueryClient(requestMetricsMode())}>
      <MemoryRouter initialEntries={name === 'Detail' ? ['/opportunities/opportunity-1'] : ['/inbox']}>{page}</MemoryRouter>
    </QueryClientProvider>)
    for (let index = 0; index < 8; index += 1) { await flush(); await new Promise<void>((resolve) => setTimeout(resolve, 0)) }
    expect(document.body.textContent).not.toMatch(/Carregando|Não foi possível/)
    mount.unmount()
    const report = remember(`cold-${name.toLowerCase()}`, metrics.report())
    expect(report.requests.length).toBeLessThanOrEqual(expectedRequests)
    expect(report.requests.length).toBeGreaterThan(0)
    expect(report.requests.every((entry) => entry.outcome === 'success')).toBe(true)
  })

  it('measures cold hook requests and a submitted Inbox search as separate product requests', async () => {
    const metrics = createHookMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient(requestMetricsMode())
    render(
      <QueryClientProvider client={client}>
        <InboxProbe />
        <AssessmentProbe />
        <OpportunityApplicationProbe />
      </QueryClientProvider>,
    )
    await flush()
    render(
      <QueryClientProvider client={client}>
        <InboxProbe search="engenharia" />
      </QueryClientProvider>,
    )
    await flush()

    const report = remember('cold-inbox-assessment-application-and-filter', metrics.report())
    expect(report.requests.filter((entry) => entry.endpoint === '/inbox')).toHaveLength(2)
    expect(report.requests.filter((entry) => entry.endpoint === '/matches')).toHaveLength(1)
    expect(report.requests.filter((entry) => entry.endpoint === '/applications')).toHaveLength(1)
  })

  it('keeps fresh hook data on a real warm unmount and remount', async () => {
    const metrics = createHookMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient(requestMetricsMode())
    const firstMount = renderMount(
      <QueryClientProvider client={client}>
        <InboxProbe />
      </QueryClientProvider>,
    )
    await flush()
    const coldRequests = metrics.report().requests.length
    firstMount.unmount()
    render(
      <QueryClientProvider client={client}>
        <InboxProbe />
      </QueryClientProvider>,
    )
    await flush()
    const warmRequests = metrics.report().requests.length
    expect(warmRequests).toBe(coldRequests + (requestMetricsMode() === 'baseline' ? 1 : 0))
    remember('warm-inbox-remount', metrics.report())
  })

  it.skipIf(requestMetricsMode() === 'baseline')('refetches a stale Inbox once after TTL expiry and remount', async () => {
    const metrics = createHookMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    vi.useFakeTimers()
    const client = createScenarioQueryClient('final')
    const firstMount = renderMount(
      <QueryClientProvider client={client}><InboxProbe /></QueryClientProvider>,
    )
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(metrics.report().requests).toHaveLength(1)
    firstMount.unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_001)
    })
    const secondMount = renderMount(
      <QueryClientProvider client={client}><InboxProbe /></QueryClientProvider>,
    )
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(metrics.report().requests).toHaveLength(2)
    secondMount.unmount()
    remember('ttl-expiry-inbox', metrics.report())
  })

  it.skipIf(requestMetricsMode() === 'baseline')('does not refetch a fresh Inbox when connectivity returns', async () => {
    const metrics = createHookMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient('final')
    const mount = renderMount(
      <QueryClientProvider client={client}><InboxProbe /></QueryClientProvider>,
    )
    await flush()
    expect(metrics.report().requests).toHaveLength(1)
    onlineManager.setOnline(false)
    onlineManager.setOnline(true)
    await flush()
    expect(metrics.report().requests).toHaveLength(1)
    mount.unmount()
    remember('reconnect-fresh-inbox', metrics.report())
  })

  it.skipIf(requestMetricsMode() === 'baseline')('refetches a stale active Inbox once when connectivity returns', async () => {
    const metrics = createHookMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient('final')
    const mount = renderMount(
      <QueryClientProvider client={client}><InboxProbe /></QueryClientProvider>,
    )
    await flush()
    expect(metrics.report().requests).toHaveLength(1)
    onlineManager.setOnline(false)
    await client.invalidateQueries({ queryKey: ['inbox'] })
    onlineManager.setOnline(true)
    await flush()
    expect(metrics.report().requests).toHaveLength(2)
    mount.unmount()
    remember('reconnect-stale-inbox', metrics.report())
  })

  it('loads the closed Pipeline tab only when the operator opens it', async () => {
    const metrics = createRequestMetricsFetch(async (request) => {
      const url = new URL(request.url)
      if (url.pathname === '/api/applications') {
        return new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 12 }))
      }
      throw new Error(`Unregistered offline fixture: ${request.method} ${url.pathname}`)
    })
    vi.stubGlobal('fetch', metrics.fetch)
    const container = render(
      <QueryClientProvider client={createScenarioQueryClient(requestMetricsMode())}>
        <MemoryRouter><PipelinePage /></MemoryRouter>
      </QueryClientProvider>,
    )
    await flush()
    await flush()
    expect(metrics.report().requests).toHaveLength(requestMetricsMode() === 'baseline' ? 2 : 1)
    const closed = container.querySelector<HTMLButtonElement>('main button[aria-pressed="false"]')
    expect(closed?.textContent).toContain('Encerradas')
    await act(async () => { closed?.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await flush()
    expect(metrics.report().requests).toHaveLength(2)
    expect(metrics.report().requests.every((entry) => entry.outcome === 'success')).toBe(true)
    container.remove()
    remember('pipeline-closed-tab', metrics.report())
  })

  it.skipIf(requestMetricsMode() === 'baseline')('refetches each active evaluation-dependent cache once after evaluation', async () => {
    const metrics = createRequestMetricsFetch(async (request) => {
      expect(new URL(request.url).pathname).toBe('/api/matches/evaluate')
      expect(request.method).toBe('POST')
      return new Response(JSON.stringify({
        id: 'assessment-1', opportunity_id: 'opportunity-1', opportunity_version: 1,
        profile_version_id: 'profile-1', rules_version: 'rules-1', taxonomy_version: 'taxonomy-1',
        input_hash: 'fixture', eligibility: 'ELIGIBLE', eligibility_details: [], verdict: 'STRONG',
        score: '0.9', confidence: '0.9', is_stale: false, assessed_at: '2040-01-01T00:00:00Z',
        factors: [], analysis: null,
      }))
    })
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient('final')
    Object.assign(evaluationCalls, { inbox: 0, overview: 0, summary: 0 })
    let run: (() => Promise<unknown>) | null = null
    const mount = renderMount(
      <QueryClientProvider client={client}>
        <EvaluationInvalidationProbe onReady={(next) => { run = next }} />
      </QueryClientProvider>,
    )
    for (let index = 0; index < 8 && run === null; index += 1) {
      await flush()
      await new Promise<void>((resolve) => setTimeout(resolve, 0))
    }
    expect(run).not.toBeNull()
    await act(async () => { await (run as () => Promise<unknown>)() })
    await flush()
    expect(evaluationCalls).toEqual({ inbox: 2, overview: 2, summary: 2 })
    mount.unmount()
    const report = remember('evaluation-write-and-active-invalidations', metrics.report())
    expect(report.requests).toEqual([
      expect.objectContaining({ method: 'POST', endpoint: '/matches/evaluate', outcome: 'success' }),
    ])
  })

  it('does not poll during five idle minutes in the final policy', async () => {
    const metrics = createHookMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient(requestMetricsMode())
    vi.useFakeTimers()
    render(
      <QueryClientProvider client={client}>
        <InboxProbe />
      </QueryClientProvider>,
    )
    await flush()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
      await vi.advanceTimersByTimeAsync(300_000)
    })
    const idleRequests = metrics.report().requests.length - 1
    expect(idleRequests).toBe(requestMetricsMode() === 'baseline' ? 20 : 0)
    remember('five-minute-idle-inbox', metrics.report())
  })

  it('records one relevance write and one active-detail invalidation refetch', async () => {
    const metrics = createHookMetrics()
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient(requestMetricsMode())
    let submit: (() => Promise<unknown>) | null = null
    render(
      <QueryClientProvider client={client}>
        <RelevanceMutationProbe onReady={(ready) => { submit = ready }} />
      </QueryClientProvider>,
    )
    await flush()
    await act(async () => {
      await submit?.()
    })
    await flush()

    const report = remember('relevance-write-and-detail-invalidation', metrics.report())
    expect(report.requests.filter((entry) => entry.endpoint === '/opportunities/:id')).toHaveLength(2)
    expect(report.requests.filter((entry) => entry.method === 'POST' && entry.endpoint === '/opportunities/:id/relevance')).toHaveLength(1)
  })

  it.skipIf(requestMetricsMode() === 'baseline')('writes one profile version and refetches every active invalidated key once', async () => {
    const activeRoutes = [
      { queryKey: ['profile', 'active'], endpoint: '/profile/active' }, { queryKey: ['inbox'], endpoint: '/inbox' },
      { queryKey: ['overview'], endpoint: '/overview' }, { queryKey: ['assessment', 'opportunity-1'], endpoint: '/matches/latest?opportunity_id=opportunity-1' },
      { queryKey: ['saved-searches', 'summary'], endpoint: '/saved-searches/summary' },
    ] as const
    let queryVersion = 1
    const metrics = createRequestMetricsFetch(async (request) => {
      if (request.method === 'GET') return new Response(JSON.stringify({ version: queryVersion }))
      expect(new URL(request.url).pathname).toBe('/api/profile/versions')
      expect(request.method).toBe('POST')
      queryVersion = 2
      return new Response(JSON.stringify({
        id: 'profile-2', number: 2, status: 'ACTIVE', profile_lock_version: 2,
        skills: [], experiences: [], projects: [], preferences: {
          work_modes: ['REMOTE'], contracts: ['FULL_TIME'], countries: ['BR'], timezone_start_hour: 9, timezone_end_hour: 18,
          compensation_min: null, compensation_max: null, compensation_currency: 'USD', compensation_period: 'YEAR',
          relocation_allowed: false, sponsorship_required: false, target_role_families: [], target_titles: [], accepted_seniorities: [],
        },
      }), { status: 201 })
    })
    vi.stubGlobal('fetch', metrics.fetch)
    await runMutationInvalidation({
      activeRoutes,
      input: { draft: { skills: [], experiences: [], projects: [], preferences: {
        workModes: ['REMOTE'], contracts: ['FULL_TIME'], countries: ['BR'], timezoneStartHour: 9, timezoneEndHour: 18,
        compensationMin: null, compensationMax: null, compensationCurrency: 'USD', compensationPeriod: 'YEAR',
        relocationAllowed: false, sponsorshipRequired: false, targetRoleFamilies: [], targetTitles: [], acceptedSeniorities: [],
      } }, expectedProfileVersion: 1, baseVersionId: 'profile-1' },
      useMutationHook: useSaveProfile,
    })
    const report = remember('profile-write-and-active-invalidations', metrics.report())
    expect(report.requests.filter(({ method }) => method === 'POST')).toEqual([expect.objectContaining({ endpoint: '/profile/versions', outcome: 'success' })])
  })

  it.skipIf(requestMetricsMode() === 'baseline')('writes one application and refetches every active invalidated key once', async () => {
    const activeRoutes = [
      { queryKey: ['applications'], endpoint: '/applications' }, { queryKey: ['overview'], endpoint: '/overview' },
      { queryKey: ['inbox'], endpoint: '/inbox' }, { queryKey: ['saved-searches', 'summary'], endpoint: '/saved-searches/summary' },
      { queryKey: ['application', 'opportunity', 'opportunity-1'], endpoint: '/applications?opportunity_id=opportunity-1' },
    ] as const
    let queryVersion = 1
    const metrics = createRequestMetricsFetch(async (request) => {
      if (request.method === 'GET') return new Response(JSON.stringify({ version: queryVersion }))
      expect(new URL(request.url).pathname).toBe('/api/applications')
      expect(request.method).toBe('POST')
      queryVersion = 2
      return new Response(JSON.stringify(applicationFixture()), { status: 201 })
    })
    vi.stubGlobal('fetch', metrics.fetch)
    await runMutationInvalidation({ activeRoutes, input: { opportunityId: 'opportunity-1' }, useMutationHook: () => useStartApplication('opportunity-1') })
    const report = remember('application-write-and-active-invalidations', metrics.report())
    expect(report.requests.filter(({ method }) => method === 'POST')).toEqual([expect.objectContaining({ endpoint: '/applications', outcome: 'success' })])
  })

  it.skipIf(requestMetricsMode() === 'baseline')('confirms one duplicate and refetches every active invalidated key once', async () => {
    const activeRoutes = [
      { queryKey: ['duplicate-candidates', 'opportunity-1'], endpoint: '/opportunities/opportunity-1/duplicate-candidates' },
      { queryKey: ['duplicate-candidates', 'opportunity-2'], endpoint: '/opportunities/opportunity-2/duplicate-candidates' },
      { queryKey: ['opportunity', 'opportunity-1'], endpoint: '/opportunities/opportunity-1' }, { queryKey: ['opportunity', 'opportunity-2'], endpoint: '/opportunities/opportunity-2' },
      { queryKey: ['inbox'], endpoint: '/inbox' }, { queryKey: ['overview'], endpoint: '/overview' }, { queryKey: ['saved-searches', 'summary'], endpoint: '/saved-searches/summary' },
    ] as const
    let queryVersion = 1
    const metrics = createRequestMetricsFetch(async (request) => {
      if (request.method === 'GET') return new Response(JSON.stringify({ version: queryVersion }))
      expect(new URL(request.url).pathname).toBe('/api/opportunities/duplicate-candidates/candidate-1/confirm')
      expect(request.method).toBe('POST')
      queryVersion = 2
      return new Response(JSON.stringify({
        id: 'candidate-1', opportunity_id: 'opportunity-1', duplicate_opportunity_id: 'opportunity-2', survivor_opportunity_id: 'opportunity-1',
        absorbed_opportunity_id: 'opportunity-2', rule: 'fixture', score: null, status: 'CONFIRMED', decided_by: 'test', decided_at: null, created_at: '2040-01-01T00:00:00Z',
      }))
    })
    vi.stubGlobal('fetch', metrics.fetch)
    await runMutationInvalidation({
      activeRoutes,
      input: { candidateId: 'candidate-1', expectedVersionSurvivor: 1, expectedVersionAbsorbed: 1, decidedBy: 'test' },
      useMutationHook: () => useConfirmDuplicate('opportunity-1', 'opportunity-2'),
    })
    const report = remember('duplicate-write-and-active-invalidations', metrics.report())
    expect(report.requests.filter(({ method }) => method === 'POST')).toEqual([expect.objectContaining({ endpoint: '/opportunities/duplicate-candidates/:id/confirm', outcome: 'success' })])
  })

  it.skipIf(requestMetricsMode() === 'baseline')('runs one manual-intake write and refetches every active invalidated key once', async () => {
    const activeRoutes = [
      { queryKey: ['source-health'], endpoint: '/source-health' }, { queryKey: ['source-coverage'], endpoint: '/sources/coverage' },
      { queryKey: ['source-metrics'], endpoint: '/source-metrics' }, { queryKey: ['overview'], endpoint: '/overview' },
      { queryKey: ['source-runs', 'source-1'], endpoint: '/source-runs?source_id=source-1' }, { queryKey: ['inbox'], endpoint: '/inbox' },
      { queryKey: ['saved-searches', 'summary'], endpoint: '/saved-searches/summary' },
    ] as const
    let queryVersion = 1
    const metrics = createRequestMetricsFetch(async (request) => {
      const path = new URL(request.url).pathname
      if (request.method === 'GET') return new Response(JSON.stringify({ version: queryVersion }))
      if (path === '/api/sources/source-1/manual-intake') {
        expect(request.method).toBe('POST')
        queryVersion = 2
        return new Response(JSON.stringify({
          run: { id: 'run-1', status: 'SUCCEEDED', items_seen: 1, items_persisted: 1 }, items: [],
        }), { status: 201 })
      }
      throw new Error(`Unregistered offline fixture: ${request.method} ${path}`)
    })
    vi.stubGlobal('fetch', metrics.fetch)
    await runMutationInvalidation({
      activeRoutes,
      input: [{ kind: 'URL', value: 'https://example.com/job', metadata: {} }],
      useMutationHook: () => useManualIntake('source-1'),
    })
    const report = remember('manual-intake-single-write-and-active-invalidations', metrics.report())
    expect(report.requests.filter(({ method }) => method === 'POST')).toEqual([
      expect.objectContaining({ method: 'POST', endpoint: '/sources/:id/manual-intake', outcome: 'success' }),
    ])
  })

  it.skipIf(requestMetricsMode() === 'baseline')('retries one transient 5xx GET through the real QueryClient at most once', async () => {
    const metrics = createRequestMetricsFetch(async (request) => {
      if (request.url.endsWith('/retry-5xx')) return new Response('{}', { status: 503 })
      throw new Error(`Unregistered offline fixture: ${request.method} ${new URL(request.url).pathname}`)
    }, { isRetry: (_request, requestOrdinal) => requestOrdinal > 1 })
    vi.stubGlobal('fetch', metrics.fetch)
    onlineManager.setOnline(true)
    const client = createScenarioQueryClient('final')
    const query = client.fetchQuery({
      queryKey: ['retry-probe', 'retry-5xx'],
      networkMode: 'always',
      queryFn: async () => {
        const response = await privateFetch('/api/retry-5xx')
        if (!response.ok) throw await (apiWithFailure.failureFrom?.(response) ?? Promise.resolve(new Error('HTTP failure')))
        return response.json()
      },
    }).catch(() => undefined)
    await flush()
    vi.useFakeTimers()
    await act(async () => {
      await vi.runAllTimersAsync()
    })
    await query
    await flush()

    const report = remember('retry-5xx', metrics.report())
    expect(report.requests).toHaveLength(2)
    expect(report.requests).toEqual(expect.arrayContaining([
      expect.objectContaining({ method: 'GET', endpoint: '/retry-5xx', outcome: 'error' }),
    ]))
    expect(report.requests.map((entry) => entry.retry)).toEqual([false, true])
  })

  it.skipIf(requestMetricsMode() === 'baseline')('retries a typed GET network failure through the real QueryClient exactly once', async () => {
    const client = createScenarioQueryClient('final')
    let attempts = 0
    const query = client.fetchQuery({
      queryKey: ['retry-network'],
      networkMode: 'always',
      queryFn: async () => {
        attempts += 1
        throw new NetworkError('offline fixture', 'GET')
      },
    }).catch(() => undefined)
    await flush()
    vi.useFakeTimers()
    await vi.runAllTimersAsync()
    await query
    expect(attempts).toBe(2)
  })

  it.skipIf(requestMetricsMode() === 'baseline').each([
    ['no-retry-401', 401, false],
    ['no-retry-403', 403, false],
    ['no-retry-409', 409, false],
    ['no-retry-422', 422, false],
    ['no-retry-429', 429, false],
    ['no-retry-parser', 200, true],
  ])('does not retry a non-transient GET failure through the real QueryClient: %s', async (endpoint, status, parserFailure) => {
    const metrics = createRequestMetricsFetch(async () => new Response('{}', { status }))
    vi.stubGlobal('fetch', metrics.fetch)
    vi.useFakeTimers()
    render(
      <QueryClientProvider client={createScenarioQueryClient('final')}>
        <NonRetryQueryProbe endpoint={endpoint} parserFailure={parserFailure} />
      </QueryClientProvider>,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
      await vi.advanceTimersByTimeAsync(1_000)
    })
    await flush()
    const report = remember(endpoint, metrics.report())
    expect(report.requests).toHaveLength(1)
    expect(report.requests[0]).toEqual(expect.objectContaining({ method: 'GET', status, retry: null }))
  })

  it.skipIf(requestMetricsMode() === 'baseline')('does not retry a failed write through the real QueryClient', async () => {
    const metrics = createRequestMetricsFetch(async () => new Response('{}', { status: 500 }))
    vi.stubGlobal('fetch', metrics.fetch)
    const client = createScenarioQueryClient('final')
    let run: (() => Promise<unknown>) | null = null
    render(
      <QueryClientProvider client={client}>
        <NonRetryMutationProbe onReady={(ready) => { run = ready }} />
      </QueryClientProvider>,
    )
    await flush()
    expect(run).not.toBeNull()
    const submit = run as unknown as () => Promise<unknown>
    await expect(submit()).rejects.toBeInstanceOf(Error)
    await flush()
    const report = remember('no-retry-write', metrics.report())
    expect(report.requests).toEqual([
      expect.objectContaining({ method: 'POST', endpoint: '/write-failure', status: 500, retry: null }),
    ])
  })

  it('normalizes endpoints before recording fixture attempts', () => {
    expect(normalizedEndpoint('/api/opportunities/550e8400-e29b-41d4-a716-446655440000?email=private@example.com'))
      .toBe('/opportunities/:id')
    expect(normalizedEndpoint('/api/saved-searches/summary')).toBe('/saved-searches/summary')
    expect(normalizedEndpoint('/api/opportunities/duplicate-candidates')).toBe('/opportunities/duplicate-candidates')
    expect(normalizedEndpoint('/api/sources/coverage')).toBe('/sources/coverage')
  })

  it('records actual privateFetch attempts from an authenticated test identity', async () => {
    const metrics = createRequestMetricsFetch(async (request) => {
      if (request.url.endsWith('/overview')) {
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { 'content-length': '11' },
        })
      }
      if (request.url.endsWith('/blocked')) return new Response('{}', { status: 403 })
      if (request.url.endsWith('/signed-out')) return new Response('{}', { status: 401 })
      if (request.url.endsWith('/invalid')) return new Response('{}', { status: 422 })
      if (request.url.endsWith('/limited')) return new Response('{}', { status: 429 })
      if (request.url.endsWith('/server-error')) return new Response('{}', { status: 500 })
      throw new Error(`Unregistered offline fixture: ${request.method} ${new URL(request.url).pathname}`)
    })
    vi.stubGlobal('fetch', metrics.fetch)

    await privateFetch('/api/overview')
    await privateFetch('/api/blocked')
    await privateFetch('/api/signed-out')
    await privateFetch('/api/invalid')
    await privateFetch('/api/limited')
    await privateFetch('/api/server-error')
    await expect(privateFetch('/api/not-registered')).rejects.toThrow('Unregistered offline fixture')

    const report = remember('private-fetch-http-outcomes', metrics.report())
    expect(report.requests).toEqual([
      expect.objectContaining({ method: 'GET', endpoint: '/overview', status: 200, outcome: 'success', bytes: 11 }),
      expect.objectContaining({ method: 'GET', endpoint: '/blocked', status: 403, outcome: 'error' }),
      expect.objectContaining({ method: 'GET', endpoint: '/signed-out', status: 401, outcome: 'error' }),
      expect.objectContaining({ method: 'GET', endpoint: '/invalid', status: 422, outcome: 'error' }),
      expect.objectContaining({ method: 'GET', endpoint: '/limited', status: 429, outcome: 'error' }),
      expect.objectContaining({ method: 'GET', endpoint: '/server-error', status: 500, outcome: 'error' }),
      expect.objectContaining({ method: 'GET', endpoint: '/not-registered', status: null, outcome: 'error' }),
    ])
  })

  it('records an aborted fixture attempt separately from an HTTP failure', async () => {
    const metrics = createRequestMetricsFetch(async () => {
      throw new DOMException('cancelled by test', 'AbortError')
    })
    vi.stubGlobal('fetch', metrics.fetch)

    await expect(privateFetch('/api/inbox')).rejects.toMatchObject({ name: 'AbortError' })

    const report = remember('aborted-request', metrics.report())
    expect(report.requests[0]).toEqual(
      expect.objectContaining({ endpoint: '/inbox', status: null, outcome: 'cancelled' }),
    )
  })

  it('separates session and preflight attempts from product request totals', async () => {
    const metrics = createRequestMetricsFetch(async () => new Response('{}', { status: 200 }))
    await metrics.fetch('/api/session')
    await metrics.fetch('/api/inbox', { method: 'OPTIONS' })

    const report = remember('session-and-preflight-separation', metrics.report())
    expect(report.requests.map((entry) => entry.trafficKind)).toEqual(['auth-session', 'preflight'])
  })
})
