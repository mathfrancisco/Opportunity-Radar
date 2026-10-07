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
  it.each(['workday', 'teamtailor', 'workable', 'factorial', 'jobposting', 'inhire'])(
    'mostra o card da fonte %s com o tipo e o botão de execução',
    async (sourceType) => {
      stubFetch([healthItem(sourceType)])

      const container = renderPage(<SourcesPage />)
      await flush()

      expect(container.textContent).toContain(sourceType)
      const runButton = [...container.querySelectorAll('button')].find(
        (button) => button.textContent === 'Executar agora',
      )
      expect(runButton).toBeDefined()
      expect(runButton?.disabled).toBe(false)
    },
  )

  it('mostra todos os ATS novos ao mesmo tempo, cada um com seu próprio card', async () => {
    const types = ['workday', 'teamtailor', 'workable', 'factorial', 'jobposting', 'inhire']
    stubFetch(types.map((sourceType) => healthItem(sourceType)))

    const container = renderPage(<SourcesPage />)
    await flush()

    for (const sourceType of types) {
      expect(container.textContent).toContain(sourceType)
    }
    expect(container.querySelectorAll('tbody tr').length).toBe(types.length)
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

describe('SourcesPage — tabela e ação de cabeçalho', () => {
  it('expõe o kicker de aquisição e associa os erros do formulário aos campos', async () => {
    stubFetch([healthItem('greenhouse')])

    const container = renderPage(<SourcesPage />)
    await flush()

    expect(container.querySelector('header')?.textContent).toContain('Aquisição')

    const add = [...container.querySelectorAll<HTMLButtonElement>('header button')].find(
      (button) => button.textContent === 'Adicionar fonte',
    )
    act(() => add?.click())
    await flush()

    const name = [...container.querySelectorAll('input')].find(
      (input) => input.closest('label')?.textContent?.includes('Nome'),
    )
    expect(name?.closest('label')?.textContent).toContain('Nome')
    expect(
      container.querySelector(`#${name?.getAttribute('aria-labelledby')}`)?.textContent,
    ).toBe('Nome')

    const submit = [...container.querySelectorAll('button')].find(
      (button) => button.textContent === 'Criar fonte desabilitada',
    )
    act(() => submit?.click())
    await flush()

    const errorIds = name?.getAttribute('aria-describedby')?.split(' ') ?? []
    expect(name?.getAttribute('aria-invalid')).toBe('true')
    expect(errorIds.some((id) => container.querySelector(`#${id}`)?.textContent === 'Dê um nome à fonte.')).toBe(true)
  })

  it('põe "Adicionar fonte" no cabeçalho, secundário, e abre o formulário de criação', async () => {
    stubFetch([healthItem('greenhouse')])

    const container = renderPage(<SourcesPage />)
    await flush()

    const add = [...container.querySelectorAll('header button')].find(
      (button) => button.textContent === 'Adicionar fonte',
    )
    expect(add).toBeDefined()
    expect(add?.className).toContain('border-line-strong')
    expect(add?.className).not.toContain('bg-ink')

    act(() => (add as HTMLButtonElement | undefined)?.click())
    await flush()

    expect(container.textContent).toContain('Nova fonte')
    // A ação sai do cabeçalho enquanto o formulário está aberto.
    expect(
      [...container.querySelectorAll('header button')].some(
        (button) => button.textContent === 'Adicionar fonte',
      ),
    ).toBe(false)
  })

  it('mostra nome em destaque, tipo em texto secundário e "Executar agora" secundário sm', async () => {
    stubFetch([healthItem('workday')])

    const container = renderPage(<SourcesPage />)
    await flush()

    const row = container.querySelector('tbody tr')
    expect(row?.querySelector('.font-semibold')?.textContent).toBe('Fonte workday')
    expect(row?.querySelector('.text-muted')?.textContent).toBe('workday')
    const run = [...(row?.querySelectorAll('button') ?? [])].find(
      (button) => button.textContent === 'Executar agora',
    )
    expect(run?.className).toContain('h-8')
    expect(run?.className).toContain('border-line-strong')
  })

  it('abre o histórico numa linha logo abaixo da fonte', async () => {
    stubFetch([healthItem('workday')])

    const container = renderPage(<SourcesPage />)
    await flush()
    expect(container.querySelectorAll('tbody tr')).toHaveLength(1)

    const toggle = [...container.querySelectorAll('button')].find(
      (button) => button.textContent === 'Ver execuções',
    )
    act(() => toggle?.click())
    await flush()

    expect(toggle?.getAttribute('aria-expanded')).toBe('true')
    expect(container.querySelectorAll('tbody > tr').length).toBeGreaterThanOrEqual(2)
  })

  it('filtra a lista carregada por estado e nome, e permite limpar os filtros', async () => {
    stubFetch([
      healthItem('workday', { last_run_status: 'SUCCEEDED' }),
      healthItem('manual', { last_run_status: 'PARTIAL' }),
      healthItem('greenhouse', { last_run_status: 'FAILED' }),
    ])

    const container = renderPage(<SourcesPage />)
    await flush()

    const state = container.querySelector('#source-state') as HTMLSelectElement
    act(() => {
      state.value = 'failing'
      state.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(container.textContent).toContain('Exibindo 2 de 3 fontes carregadas.')
    expect(container.textContent).not.toContain('Fonte workday')

    const search = container.querySelector('#source-search') as HTMLInputElement
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      setter?.call(search, 'manual')
      search.dispatchEvent(new Event('input', { bubbles: true }))
    })
    expect(container.textContent).toContain('Exibindo 1 de 3 fontes carregadas.')
    expect(container.textContent).toContain('Fonte manual')
    expect(container.textContent).not.toContain('Fonte greenhouse')

    const reset = [...container.querySelectorAll('button')].find(
      (button) => button.textContent === 'Limpar filtros',
    )
    act(() => reset?.click())
    expect(container.textContent).toContain('Exibindo 3 de 3 fontes carregadas.')
  })

  it('mantém ações secundárias e a orientação de bloqueio em uma divulgação compacta', async () => {
    stubFetch([healthItem('workday', { enabled: false })])

    const container = renderPage(<SourcesPage />)
    await flush()

    const disclosure = container.querySelector('details') as HTMLDetailsElement
    expect(disclosure.open).toBe(false)
    expect(disclosure.querySelector('summary')?.textContent).toBe('Mais ações')
    expect(disclosure.textContent).toContain('Fonte desabilitada: habilite na homologação')

    const history = [...disclosure.querySelectorAll('button')].find(
      (button) => button.textContent === 'Ver execuções',
    )
    act(() => history?.click())
    await flush()

    expect(history?.getAttribute('aria-expanded')).toBe('true')
    expect(container.querySelectorAll('tbody > tr').length).toBeGreaterThanOrEqual(2)
  })
})
