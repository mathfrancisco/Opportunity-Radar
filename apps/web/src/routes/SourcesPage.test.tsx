import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { SourcesPage } from './SourcesPage'

afterEach(() => vi.unstubAllGlobals())

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderPage(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Minimal `/source-health` item for one collector, homologated and enabled. */
function healthItem(sourceType: string, overrides: Record<string, unknown> = {}) {
  return {
    source_definition_id: `source-${sourceType}`,
    name: `Fonte ${sourceType}`,
    source_type: sourceType,
    enabled: true,
    evidence_status: 'confirmed',
    terms_reviewed: true,
    collector_local_tested: true,
    schedule: null,
    version: 1,
    last_run_id: null,
    last_run_status: null,
    last_run_started_at: null,
    last_run_finished_at: null,
    last_run_duration_seconds: null,
    last_run_error_code: null,
    last_run_error: null,
    last_run_items_seen: null,
    last_run_items_persisted: null,
    last_run_items_skipped: null,
    last_run_items_invalid: null,
    seniority_counts: {},
    ...overrides,
  }
}

function coverage() {
  return {
    catalog_companies: 10,
    catalog_source_records: 10,
    proposed_sources: 0,
    homologated_sources: 5,
    enabled_sources: 5,
    eligible_sources: 5,
  }
}

/** Routes /source-health and /source-coverage by URL, same shape production sends. */
function stubFetch(items: ReturnType<typeof healthItem>[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      const url = String(input)
      if (url.includes('/source-health')) {
        return new Response(
          JSON.stringify({ items, total: items.length, failing: 0 }),
          { status: 200 },
        )
      }
      if (url.includes('/source-coverage')) {
        return new Response(JSON.stringify(coverage()), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    }),
  )
}

// F20 §5: Overview and Sources had no component test covering the ATS types added
// after the collector work landed (workday, teamtailor, workable, factorial, plus the
// generic jobposting collector) — this proves each renders its card correctly instead
// of falling back to "unknown" or crashing the list.
describe('SourcesPage — novos ATS', () => {
  it.each(['workday', 'teamtailor', 'workable', 'factorial', 'jobposting'])(
    'mostra o card da fonte %s com o tipo e o botão de execução',
    async (sourceType) => {
      stubFetch([healthItem(sourceType)])

      const container = renderPage(<SourcesPage />)
      await flush()

      expect(container.textContent).toContain(`(${sourceType})`)
      const runButton = [...container.querySelectorAll('button')].find(
        (button) => button.textContent === 'Executar agora',
      )
      expect(runButton).toBeDefined()
      expect(runButton?.disabled).toBe(false)
    },
  )

  it('mostra todos os ATS novos ao mesmo tempo, cada um com seu próprio card', async () => {
    const types = ['workday', 'teamtailor', 'workable', 'factorial', 'jobposting']
    stubFetch(types.map((sourceType) => healthItem(sourceType)))

    const container = renderPage(<SourcesPage />)
    await flush()

    for (const sourceType of types) {
      expect(container.textContent).toContain(`(${sourceType})`)
    }
    expect(container.querySelectorAll('article').length).toBe(types.length)
  })

  it('desabilita a execução de uma fonte não homologada, independente do ATS', async () => {
    stubFetch([healthItem('workday', { enabled: false })])

    const container = renderPage(<SourcesPage />)
    await flush()

    const runButton = [...container.querySelectorAll('button')].find(
      (button) => button.textContent === 'Executar agora',
    )
    expect(runButton?.disabled).toBe(true)
    expect(container.textContent).toContain('Fonte desabilitada')
  })
})
