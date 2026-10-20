import { installTestAuth } from '../test/auth'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HomologationQueue } from './HomologationQueue'
import { render, visibleTextOutsideDetails } from './testing'

afterEach(() => vi.unstubAllGlobals())

const pendingFetches: (() => void)[] = []

/** A fetch that stays open until `settlePending`, so no request outlives its test. */
function holdFetch(): Promise<Response> {
  return new Promise<Response>((resolve) => {
    pendingFetches.push(() => resolve(new Response('{}', { status: 500 })))
  })
}

async function settlePending() {
  await act(async () => {
    pendingFetches.splice(0).forEach((release) => release())
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

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
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
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
  detail?: Record<string, unknown>
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
        return new Response(JSON.stringify(sourceDetail(sourceIdMatch[1], options.detail)), {
          status: 200,
        })
      }
      return new Response('{}', { status: 200 })
    }),
  )
  return calls
}

describe('HomologationQueue', () => {
  it('carregando: mostra o esqueleto da fila', async () => {
    vi.stubGlobal('fetch', vi.fn(() => holdFetch()))

    const container = renderWithClient(<HomologationQueue />)
    await flush(1)

    expect(container.querySelector('[aria-busy="true"]')?.textContent).toContain(
      'Carregando a fila de homologação…',
    )
    await settlePending()
  })

  it('vazio: diz o próximo passo e leva às fontes', async () => {
    stubFetch({ items: [] })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    expect(container.textContent).toContain('Nenhuma proposta aguardando.')
    expect(container.querySelector('a[href="/sources"]')?.textContent).toBe('Ver as fontes')
  })

  it('erro: diz o que continua valendo e oferece tentar de novo', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })))

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    const alert = container.querySelector('[role="alert"]')
    expect(alert?.textContent).toContain('As fontes já habilitadas continuam coletando.')
    expect(alert?.querySelector('button')?.textContent).toBe('Tentar novamente')
  })

  it('parcial: resume o lote quando parte das fontes não passou', async () => {
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
            detail: null,
            evidence_recorded: false,
            finished_at: null,
            retry_after_seconds: 0,
          },
          source: sourceDetail('source-1'),
        },
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()
    act(() => container.querySelector<HTMLInputElement>('input[aria-label="Selecionar todas as propostas"]')?.click())
    await flush()
    const batchButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.startsWith('Testar selecionadas'),
    )
    act(() => batchButton?.click())
    await flush()
    await flush()

    expect(container.textContent).toContain(
      '1 de 2 fontes testadas. 1 não passou e segue como proposta.',
    )
  })

  it('não mostra código técnico no texto visível', async () => {
    stubFetch({
      detail: { evidence_status: 'ats_identified' },
      items: [
        healthItem({ source_definition_id: 'source-1', name: 'Limitada', evidence_status: 'ats_identified' }),
      ],
      probeResponses: [
        {
          probe: {
            id: 'probe-1',
            status: 'FAILED',
            items_seen: 0,
            http_requests: 1,
            error_code: 'SOURCE_RATE_LIMITED',
            detail: 'limite',
            evidence_recorded: false,
            finished_at: null,
            retry_after_seconds: 0,
          },
          source: sourceDetail('source-1'),
        },
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()
    act(() => container.querySelector<HTMLInputElement>('input[aria-label="Selecionar Limitada"]')?.click())
    await flush()
    act(() =>
      Array.from(container.querySelectorAll('button'))
        .find((button) => button.textContent?.startsWith('Testar selecionadas'))
        ?.click(),
    )
    await flush()
    await flush()
    expect(visibleTextOutsideDetails(container)).not.toMatch(/[A-Z]{3,}_[A-Z_]+/)

    act(() => container.querySelector<HTMLButtonElement>('tbody tr button')?.click())
    await flush()
    const sequential = visibleTextOutsideDetails(container)
    expect(sequential).toContain('Evidência sistema identificado')
    expect(sequential).not.toMatch(/[A-Z]{3,}_[A-Z_]+/)
    expect(sequential).not.toContain('ats_identified')
    expect(sequential).not.toContain('board_token')
  })

  it('mostra o tipo da fonte em português, sem o código', async () => {
    stubFetch({
      items: [
        healthItem({ source_definition_id: 'source-1', name: 'Primeira', source_type: 'tavily_search' }),
        healthItem({ source_definition_id: 'source-2', name: 'Segunda', source_type: 'novo_coletor' }),
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    const visible = visibleTextOutsideDetails(container)
    expect(visible).toContain('Busca na web (Tavily)')
    expect(visible).toContain('Tipo não reconhecido')
    expect(visible).not.toMatch(/\b[a-z]+(?:_[a-z]+)+\b/)
  })

  it('o teste individual usa o mesmo verbo do botão na confirmação', async () => {
    stubFetch({ items: [healthItem({ source_definition_id: 'source-1', name: 'Primeira' })] })

    const container = renderWithClient(<HomologationQueue />)
    await flush()
    act(() => container.querySelector<HTMLButtonElement>('tbody tr button')?.click())
    await flush()
    const test = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'Testar a fonte',
    )
    act(() => test?.click())
    await flush()

    expect(container.textContent).toContain('Fonte testada. Leu 1 item.')
  })

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

    const names = Array.from(container.querySelectorAll('tbody tr')).map((item) => item.textContent)
    expect(names[0]).toContain('Alta prioridade')
    expect(names[0]).toContain('Sem teste')
    expect(names[1]).toContain('Confirmada')
    expect(names[1]).toContain('Evidência confirmada')
  })

  it('usa DataTable, chip de estado e "Homologar" sm abre o modo sequencial na linha', async () => {
    stubFetch({
      items: [
        healthItem({ source_definition_id: 'source-1', name: 'Primeira' }),
        healthItem({ source_definition_id: 'source-2', name: 'Segunda' }),
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    expect(container.querySelector('table')).not.toBeNull()
    expect(container.querySelector('tbody tr span.rounded-chip')?.textContent).toBe('Sem teste')
    const second = container.querySelectorAll('tbody tr')[1]
    const button = second.querySelector('button')
    expect(button?.textContent).toBe('Homologar')
    expect(button?.className).toContain('h-8')
    act(() => button?.click())
    await flush()

    expect(container.textContent).toContain('2 de 2')
    expect(container.textContent).toContain('Fonte source-2')
  })

  it('mostra a evidência de homologação aninhada, nunca [object Object] (R55-D6)', async () => {
    stubFetch({
      items: [healthItem({ source_definition_id: 'source-1', name: 'Primeira' })],
      detail: {
        configuration: {
          board_token: 'acme',
          homologation_audit: {
            terms_review: 'operator-confirmed via --accept-terms',
            collector_local_test: { status: 'passed', items_seen: 3, http_requests: 1 },
          },
        },
      },
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()
    act(() => container.querySelector<HTMLButtonElement>('tbody tr button')?.click())
    await flush()

    const text = container.textContent ?? ''
    expect(text).not.toContain('[object Object]')
    expect(text).toContain('homologation_audit')
    expect(text).toContain('terms_review')
    expect(text).toContain('operator-confirmed via --accept-terms')
    expect(text).toContain('collector_local_test')
    expect(text).toContain('items_seen')
    expect(text).toContain('passed')
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
      (button) => button.textContent === 'Revisar uma a uma',
    )
    expect(sequentialButton).toBeDefined()
    act(() => sequentialButton?.click())
    await flush()

    expect(container.textContent).toContain('Revisão uma a uma')
    expect(container.querySelector('progress')?.getAttribute('value')).toBe('0')
    expect(container.querySelector('progress')?.getAttribute('max')).toBe('2')
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
    expect(container.querySelector('progress')?.getAttribute('value')).toBe('1')
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

    const first = container.querySelector<HTMLInputElement>('input[aria-label="Selecionar Limitada"]')
    const second = container.querySelector<HTMLInputElement>('input[aria-label="Selecionar Confirmada"]')
    expect(first).not.toBeNull()
    expect(second).not.toBeNull()
    act(() => first?.click())
    act(() => second?.click())
    await flush()

    const batchButton = Array.from(container.querySelectorAll('button')).find((button) =>
      button.textContent?.startsWith('Testar selecionadas'),
    )
    expect(batchButton).toBeDefined()
    act(() => batchButton?.click())
    await flush()
    await flush()

    const rows = Array.from(container.querySelectorAll('tbody tr'))
    expect(rows[0].textContent).toContain('SOURCE_RATE_LIMITED')
    expect(rows[0].textContent).toContain('Aguarde 0s antes de tentar de novo')
    expect(rows[1].textContent).toContain('Fonte testada.')
  })

  it('seleciona todas as propostas e destaca as linhas selecionadas', async () => {
    stubFetch({
      items: [
        healthItem({ source_definition_id: 'source-1', name: 'Primeira' }),
        healthItem({ source_definition_id: 'source-2', name: 'Segunda' }),
      ],
    })

    const container = renderWithClient(<HomologationQueue />)
    await flush()

    const selectAll = container.querySelector<HTMLInputElement>(
      'input[aria-label="Selecionar todas as propostas"]',
    )
    expect(selectAll).not.toBeNull()
    act(() => selectAll?.click())
    await flush()

    expect(container.textContent).toContain('2 selecionadas')
    expect(container.querySelectorAll('tbody tr[aria-selected="true"]')).toHaveLength(2)
    expect(selectAll?.checked).toBe(true)
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

installTestAuth()
