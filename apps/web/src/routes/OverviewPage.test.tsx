import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { App } from '../app/App'
import { render } from '../components/testing'
import { OverviewPage, SavedSearchesWithNews, StartupShortcut } from './OverviewPage'

afterEach(() => vi.unstubAllGlobals())

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderWithProviders(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function savedSearch(overrides: Record<string, unknown> = {}) {
  return {
    id: 'saved-1',
    name: 'Backend remoto',
    term: 'backend',
    filters: { work_mode: 'REMOTE' },
    last_opened_at: null,
    created_at: '2040-01-01T00:00:00Z',
    ...overrides,
  }
}

/** Routes /saved-searches (list) and /saved-searches/{id}/new-count by URL. */
function stubFetch(searches: ReturnType<typeof savedSearch>[], counts: Record<string, number>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/saved-searches') && (!init || init.method === undefined || init.method === 'GET')) {
        return new Response(JSON.stringify(searches), { status: 200 })
      }
      const newCountMatch = url.match(/\/saved-searches\/([^/]+)\/new-count$/)
      if (newCountMatch) {
        const id = newCountMatch[1]
        return new Response(JSON.stringify({ new_count: counts[id] ?? 0 }), { status: 200 })
      }
      const openMatch = url.match(/\/saved-searches\/([^/]+)$/)
      if (openMatch && init?.method === 'PATCH') {
        const found = searches.find((item) => item.id === openMatch[1])
        return new Response(JSON.stringify(found), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    }),
  )
}

describe('SavedSearchesWithNews', () => {
  it('não mostra nada quando não há busca salva', async () => {
    stubFetch([], {})

    const container = renderWithProviders(<SavedSearchesWithNews />)
    await flush()

    expect(container.textContent).toBe('')
  })

  it('não mostra nada quando nenhuma busca salva tem novidade', async () => {
    stubFetch([savedSearch()], { 'saved-1': 0 })

    const container = renderWithProviders(<SavedSearchesWithNews />)
    await flush()
    await flush()

    expect(container.textContent).toBe('')
  })

  it('mostra só as buscas com novidade, com nome, contagem e link para a Inbox filtrada', async () => {
    stubFetch(
      [
        savedSearch({ id: 'saved-1', name: 'Backend remoto' }),
        savedSearch({
          id: 'saved-2',
          name: 'Dados pleno LATAM',
          filters: { seniority: 'MID', area: ['DATA'] },
        }),
      ],
      { 'saved-1': 0, 'saved-2': 3 },
    )

    const container = renderWithProviders(<SavedSearchesWithNews />)
    await flush()
    await flush()
    await flush()

    expect(container.textContent).toContain('Buscas salvas com novidade')
    expect(container.textContent).not.toContain('Backend remoto')
    expect(container.textContent).toContain('Dados pleno LATAM')
    expect(container.textContent).toContain('3')

    const link = container.querySelector('a')
    expect(link?.getAttribute('href')).toBe('/inbox?seniority=MID&area=DATA')
  })

  it('clicar na busca com novidade marca last_opened_at (abre a busca)', async () => {
    stubFetch([savedSearch({ id: 'saved-1', name: 'Backend remoto' })], { 'saved-1': 2 })

    const container = renderWithProviders(<SavedSearchesWithNews />)
    await flush()
    await flush()
    await flush()

    const link = container.querySelector('a') as HTMLAnchorElement
    act(() => link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })))
    await flush()

    expect(fetch).toHaveBeenCalledWith(
      '/api/saved-searches/saved-1',
      expect.objectContaining({ method: 'PATCH' }),
    )
  })
})

/** Minimal `/overview` body; every count defaults through `count()` to 0. */
function overviewBody(overrides: Record<string, unknown> = {}) {
  return {
    opportunities_total: 0,
    opportunities_active: 0,
    new_opportunities: 0,
    new_opportunity_window_days: 7,
    assessed_opportunities: 0,
    verdict_counts: {},
    analyses_degraded: 0,
    sources_total: 5,
    sources_enabled: 5,
    sources_failing: 0,
    failing_sources: [],
    pending_normalizations: 0,
    applications_active: 0,
    applications_by_stage: {},
    follow_ups_due: 0,
    follow_up_window_days: 7,
    precision_percent: null,
    precision_marked_count: 0,
    companies_covered: 0,
    companies_with_ats: 0,
    ...overrides,
  }
}

function failingSource(sourceType: string) {
  return {
    source_definition_id: `source-${sourceType}`,
    name: `Fonte ${sourceType}`,
    source_type: sourceType,
    enabled: true,
    last_run_status: 'FAILED',
    last_run_finished_at: '2040-01-01T00:00:00Z',
    last_run_error: 'timeout',
  }
}

/** One `/source-metrics` row per ATS type, all `SUCCEEDED`, no incidents. */
function sourceMetricsRow(sourceType: string) {
  return {
    source_definition_id: `source-${sourceType}`,
    name: `Fonte ${sourceType}`,
    source_type: sourceType,
    enabled: true,
    schedule: null,
    coverage_state: 'SUCCEEDED',
    runs: 1,
    runs_succeeded: 1,
    runs_partial: 0,
    runs_failed: 0,
    items_seen: 2,
    items_persisted: 2,
    items_skipped: 0,
    items_invalid: 0,
    latency_p95_seconds: 1.2,
    error_rate: 0,
    dedupe_rate: 0,
    has_runs: true,
    errors_by_code: {},
    seniority: {
      counts: {},
      percentages: {},
      known: 0,
      unknown: 0,
      total: 0,
      mapping_versions: {},
      evidence: {},
    },
    incident_open: false,
  }
}

const disabledAnalysisMetrics = {
  generated_at: '2040-01-01T00:00:00Z',
  current_model: '',
  pending: 0,
  windows: [],
  ai: { state: 'disabled', window_hours: 24, by_model: [], cache_hit_rate: null },
}

/** Routes /overview, /source-metrics, /analysis-metrics and /saved-searches by URL. */
function stubOverviewFetch(overview: ReturnType<typeof overviewBody>, sourceTypes: string[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      const url = String(input)
      if (url.endsWith('/saved-searches')) return new Response('[]', { status: 200 })
      if (url.endsWith('/overview')) return new Response(JSON.stringify(overview), { status: 200 })
      if (url.endsWith('/analysis-metrics')) {
        return new Response(JSON.stringify(disabledAnalysisMetrics), { status: 200 })
      }
      if (url.endsWith('/source-metrics')) {
        return new Response(
          JSON.stringify({
            generated_at: '2040-01-01T00:00:00Z',
            windows: [
              { window: '24h', since: '', until: '', sources: sourceTypes.map(sourceMetricsRow) },
              { window: '7d', since: '', until: '', sources: [] },
            ],
          }),
          { status: 200 },
        )
      }
      return new Response('{}', { status: 404 })
    }),
  )
}

// F20 §5: the Overview page had no component test covering the ATS types added after
// the collector work (workday, teamtailor, workable, factorial, jobposting) — this
// proves the failing-sources list and the per-source metrics table both render them by
// name instead of dropping to "unknown" or crashing.
describe('OverviewPage — novos ATS', () => {
  const newAtsTypes = ['workday', 'teamtailor', 'workable', 'factorial', 'jobposting']

  it('lista fontes com falha dos novos ATS, com nome e tipo', async () => {
    stubOverviewFetch(
      overviewBody({
        sources_failing: newAtsTypes.length,
        failing_sources: newAtsTypes.map(failingSource),
      }),
      [],
    )

    const container = renderWithProviders(<OverviewPage />)
    await flush(6)

    for (const sourceType of newAtsTypes) {
      expect(container.textContent).toContain(`(${sourceType})`)
    }
  })

  it('mostra a métrica por fonte de cada novo ATS na janela de 24h', async () => {
    stubOverviewFetch(overviewBody(), newAtsTypes)

    const container = renderWithProviders(<OverviewPage />)
    await flush(6)

    for (const sourceType of newAtsTypes) {
      expect(container.textContent).toContain(sourceType)
    }
    expect(container.textContent).toContain('saudáveis')
  })
})

describe('OverviewPage — orientação', () => {
  it('oferece saltos para as três seções e identifica cada destino', async () => {
    stubOverviewFetch(overviewBody(), [])

    const container = renderWithProviders(<OverviewPage />)
    await flush(6)

    const navigation = [...container.querySelectorAll('nav')].find(
      (element) => element.getAttribute('aria-label') === 'Seções da visão geral',
    )
    expect(navigation).toBeDefined()
    expect([...navigation!.querySelectorAll('a')].map((link) => link.getAttribute('href'))).toEqual([
      '#decisao-de-hoje',
      '#acervo',
      '#operacao',
    ])
    expect(container.querySelector('#decisao-de-hoje-title')?.textContent).toBe('Decisão de hoje')
    expect(container.querySelector('#acervo-title')?.textContent).toBe('Acervo')
    expect(container.querySelector('#operacao-title')?.textContent).toBe('Operação')
  })

  it('explica a janela e o instante que consolidou as métricas', async () => {
    stubOverviewFetch(overviewBody(), ['greenhouse'])

    const container = renderWithProviders(<OverviewPage />)
    await flush(6)

    expect(container.textContent).toContain('Janela: 24h.')
    expect(container.textContent).toContain('Consolidado em')
  })
})

describe('OverviewPage — composição', () => {
  it('põe a decisão antes dos números e a operação por último, na ordem do DOM', async () => {
    stubOverviewFetch(overviewBody({ new_opportunities: 2 }), [])

    const container = renderWithProviders(<OverviewPage />)
    await flush(6)

    expect(container.querySelector('h1')?.textContent).toBe('O que move sua busca esta semana?')
    const order = [...container.querySelectorAll('section[aria-labelledby]')]
      .map((section) => section.id)
      .filter((id) => ['decisao-de-hoje', 'acervo', 'operacao'].includes(id))
    expect(order).toEqual(['decisao-de-hoje', 'acervo', 'operacao'])
    // As quatro ações da decisão continuam com o rótulo e o destino de antes.
    const decision = container.querySelector('#decisao-de-hoje')!
    expect(
      [...decision.querySelectorAll('li a')].map((link) => link.getAttribute('href')),
    ).toEqual([
      '/inbox?verdict=HIGH_PRIORITY',
      '/inbox?verdict=RECOMMENDED',
      '/inbox?order=recency',
      '/applications',
    ])
    expect(
      [...container.querySelectorAll('main a[href="/inbox"]')].map((link) => link.textContent),
    ).toContain('Abrir Inbox')
  })

  it('mantém o estado vazio "nada exige decisão" e os números do acervo e da operação', async () => {
    stubOverviewFetch(overviewBody({ applications_active: 4, assessed_opportunities: 9 }), [])

    const container = renderWithProviders(<OverviewPage />)
    await flush(6)

    expect(container.querySelector('#decisao-de-hoje')?.textContent).toContain(
      'Nada exige decisão agora',
    )
    const acervo = container.querySelector('#acervo')!
    expect(acervo.querySelector('a[href="/applications"]')?.textContent).toBe('Candidaturas ativas')
    expect(acervo.querySelector('a[href="/inbox?only_assessed=true"]')?.textContent).toBe(
      'Avaliadas',
    )
    expect(container.querySelector('#operacao')?.textContent).toContain(
      'Fontes com falha na última execução',
    )
  })

  it('faz exatamente as mesmas requisições de antes, sem chamadas extras', async () => {
    stubOverviewFetch(overviewBody(), ['greenhouse'])

    renderWithProviders(<OverviewPage />)
    await flush(6)

    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls.map(([input]) => String(input))
    expect([...new Set(calls)].sort()).toEqual([
      '/api/analysis-metrics',
      '/api/overview',
      '/api/saved-searches',
      '/api/source-metrics',
    ])
    expect(calls).toHaveLength(4)
  })

  it('abrir uma busca salva com novidade continua marcando a busca como aberta', async () => {
    const search = savedSearch({ id: 'saved-1', name: 'Backend remoto' })
    const base = vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/saved-searches/saved-1/new-count')) {
        return new Response(JSON.stringify({ new_count: 2 }), { status: 200 })
      }
      if (url.endsWith('/saved-searches/saved-1') && init?.method === 'PATCH') {
        return new Response(JSON.stringify(search), { status: 200 })
      }
      if (url.endsWith('/saved-searches')) {
        return new Response(JSON.stringify([search]), { status: 200 })
      }
      if (url.endsWith('/overview')) {
        return new Response(JSON.stringify(overviewBody({ new_opportunities: 1 })), { status: 200 })
      }
      if (url.endsWith('/analysis-metrics')) {
        return new Response(JSON.stringify(disabledAnalysisMetrics), { status: 200 })
      }
      return new Response(JSON.stringify({ generated_at: '', windows: [] }), { status: 200 })
    })
    vi.stubGlobal('fetch', base)

    const container = renderWithProviders(<OverviewPage />)
    await flush(8)

    const link = [...container.querySelectorAll('a')].find(
      (anchor) => anchor.textContent === 'Backend remoto',
    ) as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('/inbox?work_mode=REMOTE')
    act(() => link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })))
    await flush()

    expect(base).toHaveBeenCalledWith(
      '/api/saved-searches/saved-1',
      expect.objectContaining({ method: 'PATCH' }),
    )
  })

  it('renderiza a Visão geral em uma URL desconhecida (rota coringa)', async () => {
    stubOverviewFetch(overviewBody(), [])
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

    const container = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/essa-rota-nao-existe']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await flush(6)

    expect(container.querySelector('h1')?.textContent).toBe('O que move sua busca esta semana?')
    expect(container.querySelector('#decisao-de-hoje')).not.toBeNull()
  })
})

// Card F20-54: the Overview links to the Inbox filtered to startups.
describe('StartupShortcut', () => {
  it('leva para a Inbox filtrada por only_startups', () => {
    const container = renderWithProviders(<StartupShortcut />)
    const link = container.querySelector('a')
    expect(link?.textContent).toBe('Ver só startups')
    expect(link?.getAttribute('href')).toBe('/inbox?only_startups=true')
  })
})
