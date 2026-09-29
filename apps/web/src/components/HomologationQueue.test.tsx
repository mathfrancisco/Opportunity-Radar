import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HomologationQueue } from './HomologationQueue'
import { render } from './testing'

afterEach(() => vi.unstubAllGlobals())

/** Flushes the micro- and macrotasks a react-query fetch resolves through. */
async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderWithClient(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>)
}

function healthItem(overrides: Record<string, unknown> = {}) {
  return {
    source_definition_id: 'source-1',
    name: 'Acme board',
    source_type: 'greenhouse',
    enabled: false,
    evidence_status: 'unverified',
    terms_reviewed: false,
    collector_local_tested: false,
    schedule: null,
    version: 1,
    last_run_id: null,
    last_run_status: null,
    last_run_started_at: null,
    last_run_finished_at: null,
    last_run_error_code: null,
    last_run_error: null,
    last_run_items_seen: null,
    last_run_items_persisted: null,
    last_run_items_skipped: null,
    last_run_items_invalid: null,
    ...overrides,
  }
}

function sourceDetail(id: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    source_type: 'greenhouse',
    name: `Fonte ${id}`,
    enabled: false,
    schedule: null,
    priority: 100,
    configuration: { board_token: id },
    evidence_status: 'unverified',
    reviewed_at: null,
    terms_reviewed: false,
    collector_local_tested: false,
    version: 1,
    ...overrides,
  }
}

/** Routes every request the queue makes, by method and path, never a real network call. */
function stubFetch(options: {
  items: ReturnType<typeof healthItem>[]
  probeResponses?: Record<string, unknown>[]
}) {
  const calls: { method: string; url: string }[] = []
  let probeCallIndex = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ method, url })
      if (url.includes('/source-health')) {
        return new Response(
          JSON.stringify({ items: options.items, total: options.items.length, failing: 0 }),
          { status: 200 },
        )
      }
      if (url.endsWith('/probe')) {
        const body = options.probeResponses?.[probeCallIndex] ?? {
          probe: {
            id: `probe-${probeCallIndex}`,
            status: 'PASSED',
            items_seen: 1,
            http_requests: 1,
            error_code: null,
            detail: null,
            evidence_recorded: true,
            finished_at: '2026-09-26T00:00:00Z',
          },
          source: sourceDetail('source-1'),
        }
        probeCallIndex += 1
        return new Response(JSON.stringify(body), { status: 200 })
      }
      const sourceIdMatch = /\/sources\/([^/?]+)/.exec(url)
      if (sourceIdMatch) {
        return new Response(JSON.stringify(sourceDetail(sourceIdMatch[1])), { status: 200 })
      }
      return new Response('{}', { status: 200 })
    }),
  )
  return calls
}

describe('HomologationQueue', () => {
  it('lista as propostas por estado e prioridade', async () => {
    stubFetch({
      items: [
        healthItem({ source_definition_id: 'source-1', name: 'Alta prioridade' }),
        healthItem({
          source_definition_id: 'source-2',
          name: 'Confirmada',
          collector_local_tested: true,
        }),
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    const names = Array.from(container.querySelectorAll('li')).map((item) => item.textContent)
    expect(names[0]).toContain('Alta prioridade')
    expect(names[0]).toContain('Sem sonda')
    expect(names[1]).toContain('Confirmada')
    expect(names[1]).toContain('Evidência confirmada')
  })

  it('modo sequencial avança sem voltar à lista', async () => {
    stubFetch({
      items: [
        healthItem({ source_definition_id: 'source-1', name: 'Primeira' }),
        healthItem({ source_definition_id: 'source-2', name: 'Segunda' }),
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    const sequentialButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Modo sequencial',
    )
    expect(sequentialButton).toBeDefined()
    act(() => sequentialButton?.click())
    await flush()

    // The list (batch button, counters grid) is gone once in sequential mode.
    expect(
      Array.from(container.querySelectorAll('button')).some((button) =>
        button.textContent?.startsWith('Testar selecionadas'),
      ),
    ).toBe(false)
    expect(container.textContent).toContain('Fonte source-1')

    const nextButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Próxima',
    )
    expect(nextButton).toBeDefined()
    act(() => nextButton?.click())
    await flush()

    expect(container.textContent).toContain('Fonte source-2')
    // Still never back at the list.
    expect(
      Array.from(container.querySelectorAll('button')).some((button) =>
        button.textContent?.startsWith('Testar selecionadas'),
      ),
    ).toBe(false)
  })

  it('lote de sondas respeita Retry-After e mostra resultado por linha', async () => {
    stubFetch({
      items: [
        healthItem({ source_definition_id: 'source-1', name: 'Limitada' }),
        healthItem({ source_definition_id: 'source-2', name: 'Confirmada' }),
      ],
      probeResponses: [
        {
          probe: {
            id: 'probe-1',
            status: 'FAILED',
            items_seen: 0,
            http_requests: 1,
            error_code: 'SOURCE_RATE_LIMITED',
            detail: 'limite de taxa',
            evidence_recorded: false,
            finished_at: null,
            retry_after_seconds: 0,
          },
          source: sourceDetail('source-1'),
        },
        {
          probe: {
            id: 'probe-2',
            status: 'PASSED',
            items_seen: 1,
            http_requests: 1,
            error_code: null,
            detail: null,
            evidence_recorded: true,
            finished_at: '2026-09-26T00:00:00Z',
          },
          source: sourceDetail('source-2'),
        },
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    const checkboxes = Array.from(
      container.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
    )
    expect(checkboxes).toHaveLength(2)
    act(() => checkboxes[0].click())
    act(() => checkboxes[1].click())
    await flush()

    const batchButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.startsWith('Testar selecionadas'),
    )
    expect(batchButton).toBeDefined()
    act(() => batchButton?.click())
    await flush()
    await flush()

    const rows = Array.from(container.querySelectorAll('li'))
    expect(rows[0].textContent).toContain('SOURCE_RATE_LIMITED')
    expect(rows[0].textContent).toContain('aguardar 0s')
    expect(rows[1].textContent).toContain('Sonda confirmada')
  })

  it('termos e habilitação nunca disparam em lote', async () => {
    stubFetch({
      items: [healthItem({ source_definition_id: 'source-1', name: 'Única' })],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    expect(container.textContent).not.toContain('Termos revisados')
    expect(
      Array.from(container.querySelectorAll('button')).some(
        (button) => button.textContent === 'Habilitar',
      ),
    ).toBe(false)
  })
})
