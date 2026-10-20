import { installTestAuth } from '../test/auth'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, visibleTextOutsideDetails } from '../components/testing'
import { StatusPage } from './StatusPage'

vi.mock('../lib/session', () => ({
  useSession: () => ({ data: { is_owner: true }, isError: false, isPending: false }),
}))

afterEach(() => vi.unstubAllGlobals())

const pendingFetches: Array<() => void> = []

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

function sourceHealthItem(overrides: Record<string, unknown> = {}) {
  return {
    source_definition_id: 'source-1',
    name: 'Acme board',
    source_type: 'greenhouse',
    enabled: true,
    evidence_status: 'confirmed',
    terms_reviewed: true,
    collector_local_tested: true,
    schedule: '0 * * * *',
    version: 1,
    last_run_id: 'run-1',
    last_run_status: 'SUCCEEDED',
    last_run_started_at: '2026-10-17T10:00:00Z',
    last_run_finished_at: '2026-10-17T10:01:00Z',
    last_run_error_code: null,
    last_run_error: null,
    last_run_items_seen: 20,
    last_run_items_persisted: 12,
    last_run_items_skipped: 8,
    last_run_items_invalid: 0,
    ...overrides,
  }
}

/** Routes the three requests the page makes by URL: readiness, health and source health. */
function stubStatusFetch(options: {
  ai?: string
  sources?: ReturnType<typeof sourceHealthItem>[]
  sourcesStatus?: number
}) {
  const sources = options.sources ?? []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      const url = String(input)
      if (url.endsWith('/health/ready')) {
        return new Response(JSON.stringify({ status: 'ready' }), { status: 200 })
      }
      if (url.endsWith('/health')) {
        return new Response(
          JSON.stringify({ status: 'ok', ai: { status: options.ai ?? 'healthy' } }),
          { status: 200 },
        )
      }
      if (url.endsWith('/source-health')) {
        if (options.sourcesStatus && options.sourcesStatus !== 200) {
          return new Response('{}', { status: options.sourcesStatus })
        }
        const failing = sources.filter((item) => item.last_run_status === 'FAILED').length
        return new Response(JSON.stringify({ items: sources, total: sources.length, failing }), {
          status: 200,
        })
      }
      return new Response('{}', { status: 404 })
    }),
  )
}

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderPage(element: ReactElement): HTMLElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('StatusPage', () => {
  it('expõe a prontidão da API e do banco e a próxima ação quando estão disponíveis', async () => {
    stubStatusFetch({})

    const container = renderPage(<StatusPage />)
    await flush()

    expect(container.textContent).toContain('Radar pronto para começar')
    expect(container.textContent).toContain('Próxima ação')
    expect(container.textContent).toContain('A prontidão confirma que a API e a conexão com o banco de dados estão disponíveis.')
    expect(container.textContent).not.toContain('IA está indisponível')
    expect(
      [...container.querySelectorAll('a')].find((link) => link.textContent === 'Ver fontes')?.getAttribute('href'),
    ).toBe('/sources')
    expect(container.querySelector('a[href="/status"]')?.getAttribute('aria-current')).toBe('page')
    expect(container.querySelectorAll('nav [aria-current="page"]')).toHaveLength(1)
  })

  it('não diz "Ambiente local" nem "local" no texto da página, que também roda na nuvem (R55-D6)', async () => {
    stubStatusFetch({})

    const container = renderPage(<StatusPage />)
    await flush()

    const main = container.querySelector('main')?.textContent ?? container.textContent ?? ''
    expect(main).not.toContain('Ambiente local')
    expect(main).not.toMatch(/local/i)
    expect(main).toContain('Ambiente não informado')
  })

  it('apresenta estado degradado quando os sinais de saúde não estão completos', async () => {
    stubStatusFetch({ ai: 'disabled' })

    const container = renderPage(<StatusPage />)
    await flush()

    expect(container.textContent).toContain('Radar disponível com recursos limitados')
    expect(container.textContent).toContain('Confira a configuração e a saúde dos serviços')
    expect(container.textContent).toContain('IA está indisponível')
    expect([...container.querySelectorAll('a')].find((link) => link.textContent === 'Ver fontes')).toBeUndefined()
  })

  it('mostra a última execução de cada fonte, com itens e erro, pela API de saúde das fontes', async () => {
    stubStatusFetch({
      sources: [
        sourceHealthItem(),
        sourceHealthItem({
          source_definition_id: 'source-2',
          name: 'Lever board',
          source_type: 'lever',
          last_run_status: 'FAILED',
          last_run_error_code: 'HTTP_503',
          last_run_error: 'quadro indisponível',
          last_run_items_seen: 0,
          last_run_items_persisted: 0,
          last_run_items_skipped: 0,
        }),
        sourceHealthItem({
          source_definition_id: 'source-3',
          name: 'Nunca rodou',
          enabled: false,
          last_run_status: null,
          last_run_finished_at: null,
          last_run_items_seen: null,
          last_run_items_persisted: null,
          last_run_items_skipped: null,
          last_run_items_invalid: null,
        }),
      ],
    })

    const container = renderPage(<StatusPage />)
    await flush(8)

    const rows = [...container.querySelectorAll('tbody tr')].map((row) => row.textContent ?? '')
    expect(container.textContent).toContain('Métricas por fonte')
    expect(container.textContent).toContain('3 fontes')
    expect(container.textContent).toContain('1 com falha ou execução parcial')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toContain('Acme board')
    expect(rows[0]).toContain('Sucesso')
    expect(rows[0]).toContain('12 gravados / 20 vistos')
    expect(rows[0]).toContain('8 repetidos')
    expect(rows[1]).toContain('Falhou')
    expect(rows[1]).toContain('Lever board não respondeu.')
    const detail = container.querySelectorAll('tbody tr')[1].querySelector('details')
    expect(detail?.querySelector('summary')?.textContent).toBe('Detalhe técnico')
    expect(detail?.textContent).toContain('HTTP_503: quadro indisponível')
    expect(rows[2]).toContain('Nunca executada')
    expect(rows[2]).toContain('desabilitada')
  })

  it('diz que não há fontes, e não inventa métricas, quando a lista está vazia', async () => {
    stubStatusFetch({ sources: [] })

    const container = renderPage(<StatusPage />)
    await flush(8)

    expect(container.textContent).toContain('Nenhuma fonte cadastrada ainda.')
    expect(container.querySelector('tbody')).toBeNull()
  })

  it('mostra erro, sem derrubar a prontidão, quando as métricas por fonte falham', async () => {
    stubStatusFetch({ sourcesStatus: 500 })

    const container = renderPage(<StatusPage />)
    await flush(8)

    expect(container.textContent).toContain('Radar pronto para começar')
    expect(container.textContent).toContain('Não foi possível carregar as métricas por fonte')
    expect(container.textContent).toContain('O estado do ambiente acima continua valendo.')
  })

  it('mostra o esqueleto das métricas enquanto a lista de fontes carrega', async () => {
    vi.stubGlobal('fetch', vi.fn(() => holdFetch()))

    const container = renderPage(<StatusPage />)
    await flush(1)

    expect(container.querySelector('[aria-busy="true"]')?.textContent).toContain(
      'Carregando métricas por fonte…',
    )
    await settlePending()
  })

  it('com a API fora, usa tom neutro e diz o que continua valendo', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })))

    const container = renderPage(<StatusPage />)
    await flush(8)

    expect(container.textContent).toContain('Não conseguimos falar com a API agora')
    expect(container.textContent).toContain('O que já está salvo continua salvo.')
    expect(container.querySelector('[role="status"]')?.innerHTML).not.toContain('danger')
    expect(container.textContent).toContain('Tentar novamente')
  })

  it('não mostra nenhum código técnico fora de "Detalhe técnico"', async () => {
    stubStatusFetch({
      sources: [
        sourceHealthItem({
          last_run_status: 'FAILED',
          last_run_error_code: 'HTTP_503',
          last_run_error: 'quadro indisponível',
        }),
      ],
    })

    const container = renderPage(<StatusPage />)
    await flush(8)

    expect(visibleTextOutsideDetails(container)).not.toMatch(/[A-Z]{3,}_[A-Z_]+/)
    expect(container.textContent).toContain('HTTP_503')
  })
})

installTestAuth()
