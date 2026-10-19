import { installTestAuth } from '../test/auth'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { createMemoryRouter, MemoryRouter, RouterProvider, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { type SavedSearchFilters } from '../features/saved-searches/api'
import { InboxPage, SaveSearchForm, SavedSearches } from './InboxPage'
import { filtersFromParams } from './inboxFilters'

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

function clickButton(container: HTMLElement, text: string) {
  const button = Array.from(container.querySelectorAll('button')).find(
    (candidate) => candidate.textContent === text,
  )
  expect(button).toBeDefined()
  act(() => button?.click())
}

/** React tracks the input's previous value on the native element; a bare `.value =`
 * assignment does not fire the synthetic `onChange`, so tests must go through the
 * native setter before dispatching `input` (same pattern as ProfilePage.test.tsx). */
function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  act(() => {
    setter?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

describe('SaveSearchForm', () => {
  it('mantém o botão desabilitado até um nome ser digitado', () => {
    const container = renderWithProviders(
      <SaveSearchForm filters={{}} term="" />,
    )
    const button = container.querySelector('button')
    expect(button?.disabled).toBe(true)

    const input = container.querySelector('input') as HTMLInputElement
    typeInto(input, 'Minha busca')

    expect(button?.disabled).toBe(false)
  })

  it('salva com nome, termo e filtros atuais, e limpa o campo depois', async () => {
    let sentBody: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_input: unknown, init?: RequestInit) => {
        sentBody = init?.body ? JSON.parse(String(init.body)) : null
        return new Response(JSON.stringify(savedSearch()), { status: 201 })
      }),
    )

    const filters: SavedSearchFilters = { work_mode: 'REMOTE' }
    const container = renderWithProviders(
      <SaveSearchForm filters={filters} term="backend" />,
    )
    const input = container.querySelector('input') as HTMLInputElement
    typeInto(input, 'Backend remoto')

    const form = container.querySelector('form') as HTMLFormElement
    act(() => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })
    await flush()

    expect(sentBody).toEqual({
      name: 'Backend remoto',
      term: 'backend',
      filters: { work_mode: 'REMOTE' },
    })
    expect(input.value).toBe('')
  })

  it('não envia nada quando o nome é só espaços', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const container = renderWithProviders(<SaveSearchForm filters={{}} term="" />)
    const input = container.querySelector('input') as HTMLInputElement
    typeInto(input, '   ')

    const button = container.querySelector('button')
    expect(button?.disabled).toBe(true)

    const form = container.querySelector('form') as HTMLFormElement
    act(() => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })

    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('SavedSearches', () => {
  it('não mostra nada quando não há busca salva', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
    )

    const container = renderWithProviders(<SavedSearches onApply={() => {}} />)
    await flush()

    expect(container.textContent).toBe('')
  })

  it('lista as buscas salvas e aplica os filtros ao clicar no nome', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/saved-searches') && (!init || init.method === undefined || init.method === 'GET')) {
          return new Response(JSON.stringify([savedSearch()]), { status: 200 })
        }
        if (url.endsWith('/saved-searches/saved-1') && init?.method === 'PATCH') {
          return new Response(
            JSON.stringify(savedSearch({ last_opened_at: '2040-01-02T00:00:00Z' })),
            { status: 200 },
          )
        }
        return new Response('{}', { status: 404 })
      }),
    )

    let appliedFilters: SavedSearchFilters | null = null
    const container = renderWithProviders(
      <SavedSearches onApply={(filters) => (appliedFilters = filters)} />,
    )
    await flush()
    await flush()

    expect(container.textContent).toContain('Buscas salvas')
    expect(container.textContent).toContain('Backend remoto')

    clickButton(container, 'Backend remoto')
    await flush()

    expect(appliedFilters).toEqual({ work_mode: 'REMOTE' })
    expect(fetch).toHaveBeenCalledWith(
      '/api/saved-searches/saved-1',
      expect.objectContaining({ method: 'PATCH' }),
    )
  })

  it('renomear envia o novo nome e sai do modo de edição', async () => {
    let renameBody: unknown = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/saved-searches') && (!init || init.method === undefined || init.method === 'GET')) {
          return new Response(JSON.stringify([savedSearch()]), { status: 200 })
        }
        if (url.endsWith('/saved-searches/saved-1') && init?.method === 'PATCH') {
          renameBody = init.body ? JSON.parse(String(init.body)) : null
          return new Response(
            JSON.stringify(savedSearch({ name: 'Backend remoto sênior' })),
            { status: 200 },
          )
        }
        return new Response('{}', { status: 404 })
      }),
    )

    const container = renderWithProviders(<SavedSearches onApply={() => {}} />)
    await flush()
    await flush()

    clickButton(container, 'Renomear')
    const input = container.querySelector('input') as HTMLInputElement
    typeInto(input, 'Backend remoto sênior')
    clickButton(container, 'Confirmar')
    await flush()

    expect(renameBody).toEqual({ name: 'Backend remoto sênior' })
    expect(container.querySelector('input')).toBeNull()
  })

  it('remover chama o delete da busca salva', async () => {
    let deleteCalled = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown, init?: RequestInit) => {
        const url = String(input)
        if (url.endsWith('/saved-searches') && (!init || init.method === undefined || init.method === 'GET')) {
          return new Response(JSON.stringify([savedSearch()]), { status: 200 })
        }
        if (url.endsWith('/saved-searches/saved-1') && init?.method === 'DELETE') {
          deleteCalled = true
          return new Response(null, { status: 204 })
        }
        return new Response('{}', { status: 404 })
      }),
    )

    const container = renderWithProviders(<SavedSearches onApply={() => {}} />)
    await flush()
    await flush()

    clickButton(container, 'Remover')
    await flush()

    expect(deleteCalled).toBe(true)
  })
})

function inboxItem(overrides: Record<string, unknown> = {}) {
  return {
    opportunity_id: 'opp-1',
    title: 'Backend Engineer',
    company_id: null,
    company_name: 'Acme',
    company_priority: null,
    location: 'Remote',
    work_mode: 'REMOTE',
    seniority: 'SENIOR',
    contract_type: 'FULL_TIME',
    lifecycle_status: 'ACTIVE',
    role_family: 'SOFTWARE_ENGINEERING',
    published_at: '2026-09-27T00:00:00Z',
    recency_effective_date: '2026-09-27T00:00:00Z',
    date_is_estimated: false,
    opportunity_version: 1,
    assessment_id: null,
    assessment_opportunity_version: null,
    assessment_profile_version_id: null,
    current_profile_version_id: null,
    verdict: null,
    eligibility: null,
    score: null,
    confidence: null,
    rules_version: null,
    is_stale: null,
    assessed_at: null,
    analysis_status: null,
    analysis_recommended_review: null,
    analysis_summary: null,
    applied: false,
    application_id: null,
    application_stage: null,
    application_next_action_at: null,
    has_pending_duplicate: false,
    startup_strength: null,
    startup_batch: null,
    ...overrides,
  }
}

/** Card F20-61: the recency toggle defaults to on (no `only_recent` param means the
 * server's own default already applies the filter) and unchecking it sends an
 * explicit `only_recent=false` request. */
describe('InboxPage recency toggle', () => {
  it('inicia marcado e não envia only_recent (o padrão do servidor já filtra)', async () => {
    const calledUrls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        calledUrls.push(url)
        if (url.includes('/inbox')) {
          return new Response(
            JSON.stringify({
              items: [inboxItem()],
              total: 1,
              offset: 0,
              limit: 25,
              order: 'priority',
              off_filter_count: 0,
            }),
            { status: 200 },
          )
        }
        return new Response(JSON.stringify([]), { status: 200 })
      }),
    )

    const container = renderWithProviders(<InboxPage />)
    await flush()

    const toggle = Array.from(container.querySelectorAll('label')).find((label) =>
      label.textContent?.includes('Mostrar só vagas dos últimos 30 dias'),
    )
    const checkbox = toggle?.querySelector('input') as HTMLInputElement
    expect(checkbox.checked).toBe(true)
    expect(calledUrls.some((url) => url.includes('/inbox'))).toBe(true)
    expect(calledUrls.every((url) => !url.includes('only_recent'))).toBe(true)
  })

  it('ao desmarcar, envia only_recent=false e mostra "(estimada)" quando aplicável', async () => {
    const calledUrls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        calledUrls.push(url)
        if (url.includes('/inbox')) {
          return new Response(
            JSON.stringify({
              items: [
                inboxItem({
                  opportunity_id: 'opp-2',
                  published_at: null,
                  recency_effective_date: '2026-09-01T00:00:00Z',
                  date_is_estimated: true,
                }),
              ],
              total: 1,
              offset: 0,
              limit: 25,
              order: 'priority',
              off_filter_count: 0,
            }),
            { status: 200 },
          )
        }
        return new Response(JSON.stringify([]), { status: 200 })
      }),
    )

    const container = renderWithProviders(<InboxPage />)
    await flush()

    expect(container.textContent).toContain('(estimada)')

    const toggle = Array.from(container.querySelectorAll('label')).find((label) =>
      label.textContent?.includes('Mostrar só vagas dos últimos 30 dias'),
    )
    const checkbox = toggle?.querySelector('input') as HTMLInputElement
    act(() => checkbox.click())
    await flush()

    expect(calledUrls.some((url) => url.includes('/inbox') && url.includes('only_recent=false'))).toBe(
      true,
    )
  })
})

/** Card F48-16: the recency lens is a FilterPill, sends the window/lens parameters, and
 * a date that is not the source's own publication date reads "(estimada)" with a hint. */
describe('InboxPage recency lenses', () => {
  function stubInbox(items: unknown[], calledUrls: string[]) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        calledUrls.push(url)
        if (url.includes('/inbox')) {
          return new Response(
            JSON.stringify({
              items,
              total: items.length,
              offset: 0,
              limit: 25,
              order: 'priority',
              off_filter_count: 0,
            }),
            { status: 200 },
          )
        }
        return new Response(JSON.stringify([]), { status: 200 })
      }),
    )
  }

  function choose(select: HTMLSelectElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    act(() => {
      setter?.call(select, value)
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
  }

  it('oferece as lentes como FilterPill e envia recency_window_days / open_at_source', async () => {
    const calledUrls: string[] = []
    stubInbox([inboxItem()], calledUrls)

    const container = renderWithProviders(<InboxPage />)
    await flush()

    const lens = container.querySelector('#inbox-recency-lens') as HTMLSelectElement
    expect(lens).not.toBeNull()
    expect(Array.from(lens.options).map((option) => option.textContent)).toEqual([
      'Últimos 30 dias',
      'Novas (14 dias)',
      'Abertas na fonte',
    ])
    expect(calledUrls.every((url) => !url.includes('recency_window_days'))).toBe(true)

    choose(lens, 'novas')
    await flush()
    expect(
      calledUrls.some((url) => url.includes('/inbox') && url.includes('recency_window_days=14')),
    ).toBe(true)

    choose(container.querySelector('#inbox-recency-lens') as HTMLSelectElement, 'abertas')
    await flush()
    expect(
      calledUrls.some((url) => url.includes('/inbox') && url.includes('open_at_source=true')),
    ).toBe(true)
  })

  it('marca "(estimada)" quando a base é atualização da fonte, não quando é publicação', async () => {
    const calledUrls: string[] = []
    stubInbox(
      [
        inboxItem({
          opportunity_id: 'opp-upd',
          title: 'Atualizada na fonte',
          published_at: null,
          recency_effective_date: '2026-09-25T00:00:00Z',
          date_is_estimated: true,
          recency_basis: 'updated',
        }),
        inboxItem({
          opportunity_id: 'opp-pub',
          title: 'Publicada de verdade',
          recency_basis: 'published',
        }),
      ],
      calledUrls,
    )

    const container = renderWithProviders(<InboxPage />)
    await flush()

    const hints = Array.from(container.querySelectorAll('[title]')).filter((node) =>
      node.textContent?.includes('(estimada)'),
    )
    expect(hints.length).toBeGreaterThan(0)
    expect(hints.every((node) => node.getAttribute('title')?.includes('última atualização'))).toBe(
      true,
    )
    // Only the "updated" item is estimated: the published one adds no "(estimada)".
    const rowsWithEstimate = Array.from(container.querySelectorAll('tr')).filter((row) =>
      row.textContent?.includes('(estimada)'),
    )
    expect(rowsWithEstimate.every((row) => row.textContent?.includes('Atualizada na fonte'))).toBe(
      true,
    )
  })
})

/** Card F20-54: the "só startups" filter sends `only_startups=true`, is off by default,
 * and the badge shows the strength/batch without touching score or verdict. */
describe('InboxPage startup filter', () => {
  function stubInbox(items: unknown[], calledUrls: string[]) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        calledUrls.push(url)
        if (url.includes('/inbox')) {
          return new Response(
            JSON.stringify({
              items,
              total: items.length,
              offset: 0,
              limit: 25,
              order: 'priority',
              off_filter_count: 0,
            }),
            { status: 200 },
          )
        }
        return new Response(JSON.stringify([]), { status: 200 })
      }),
    )
  }

  function startupToggle(container: HTMLElement): HTMLInputElement {
    const label = Array.from(container.querySelectorAll('label')).find((candidate) =>
      candidate.textContent?.includes('Só startups'),
    )
    return label?.querySelector('input') as HTMLInputElement
  }

  it('inicia desmarcado e não envia only_startups', async () => {
    const calledUrls: string[] = []
    stubInbox([inboxItem()], calledUrls)

    const container = renderWithProviders(<InboxPage />)
    await flush()

    expect(startupToggle(container).checked).toBe(false)
    expect(calledUrls.every((url) => !url.includes('only_startups'))).toBe(true)
    expect(container.querySelector('[data-testid="startup-badge"]')).toBeNull()
  })

  it('ao marcar, envia only_startups=true', async () => {
    const calledUrls: string[] = []
    stubInbox([inboxItem()], calledUrls)

    const container = renderWithProviders(<InboxPage />)
    await flush()
    act(() => startupToggle(container).click())
    await flush()

    expect(
      calledUrls.some((url) => url.includes('/inbox') && url.includes('only_startups=true')),
    ).toBe(true)
  })

  it('mostra o selo com o batch YC e marca sinal fraco', async () => {
    const calledUrls: string[] = []
    stubInbox(
      [
        inboxItem({ startup_strength: 'strong', startup_batch: 'S24' }),
        inboxItem({ opportunity_id: 'opp-2', startup_strength: 'weak', startup_batch: null }),
      ],
      calledUrls,
    )

    const container = renderWithProviders(<InboxPage />)
    await flush()

    const badges = Array.from(container.querySelectorAll('[data-testid="startup-badge"]')).map(
      (badge) => badge.textContent?.replace(/\s+/g, ' ').trim(),
    )
    expect(badges).toEqual(['Startup · YC S24', 'Startup (sinal fraco)'])
  })

  it('mostra "+N locais" só na vaga agrupada (F48-10)', async () => {
    const calledUrls: string[] = []
    stubInbox(
      [
        inboxItem({ sibling_count: 99 }),
        inboxItem({ opportunity_id: 'opp-2', sibling_count: 1 }),
        inboxItem({ opportunity_id: 'opp-3' }),
      ],
      calledUrls,
    )

    const container = renderWithProviders(<InboxPage />)
    await flush()

    const chips = Array.from(container.querySelectorAll('[data-testid="sibling-chip"]')).map(
      (chip) => chip.textContent?.replace(/\s+/g, ' ').trim(),
    )
    expect(chips).toContain('+99 locais')
    expect(chips).toContain('+1 local')
    expect(chips.some((text) => text?.startsWith('+0'))).toBe(false)
  })
})

/** Card F46-07: table rows, pagination, page size and the "Buscas salvas" dropdown. */
describe('InboxPage table, pagination and filters', () => {
  function stubInbox(total: number, calledUrls: string[], items = [inboxItem()]) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        calledUrls.push(url)
        if (url.includes('/inbox')) {
          return new Response(
            JSON.stringify({
              items,
              total,
              offset: 0,
              limit: 25,
              order: 'priority',
              off_filter_count: 0,
            }),
            { status: 200 },
          )
        }
        if (url.includes('/saved-searches')) {
          return new Response(JSON.stringify([savedSearch()]), { status: 200 })
        }
        return new Response(JSON.stringify([]), { status: 200 })
      }),
    )
  }

  function Probe() {
    const location = useLocation()
    return <output data-testid="location">{location.search}</output>
  }

  function renderAt(path: string): HTMLElement {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <InboxPage />
          <Probe />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  function search(container: HTMLElement): URLSearchParams {
    return new URLSearchParams(container.querySelector('[data-testid="location"]')?.textContent ?? '')
  }

  function choose(select: HTMLSelectElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    act(() => {
      setter?.call(select, value)
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
  }

  it('desenha a oportunidade como linha de tabela com decisão, duplicata e selo de startup', async () => {
    const urls: string[] = []
    stubInbox(
      1,
      urls,
      [
        inboxItem({
          verdict: 'STRONG_MATCH',
          has_pending_duplicate: true,
          startup_strength: 'strong',
          startup_batch: 'S24',
        }),
      ],
    )
    const container = renderAt('/inbox')
    await flush()

    const row = container.querySelector('tbody tr') as HTMLElement
    expect(row).not.toBeNull()
    expect(row.textContent).toContain('Backend Engineer')
    expect(row.textContent).toContain('Acme · Remote')
    expect(row.textContent).toContain('Possível duplicata')
    expect(row.querySelector('[data-testid="startup-badge"]')).not.toBeNull()
    expect(row.textContent).toContain('Não é para mim')
    expect(container.textContent).toContain('1 oportunidade encontrada.')
  })

  it('sincroniza busca submetida e filtros ao navegar para trás e para frente no histórico do Router', async () => {
    const urls: string[] = []
    stubInbox(1, urls)
    const router = createMemoryRouter([
      { path: '/inbox', element: <><InboxPage /><Probe /></> },
    ], { initialEntries: ['/inbox?search=backend'] })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const container = render(
      <QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>,
    )
    await flush()
    const input = container.querySelector('#inbox-search') as HTMLInputElement
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
    act(() => {
      setter?.call(input, 'plataforma')
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.closest('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    })
    await flush()
    expect(search(container).get('search')).toBe('plataforma')
    choose(container.querySelector('#inbox-verdict') as HTMLSelectElement, 'RECOMMENDED')
    await flush()
    expect(search(container).get('verdict')).toBe('RECOMMENDED')
    act(() => { void router.navigate(-1) })
    await flush()
    expect(search(container).get('search')).toBe('plataforma')
    expect(search(container).get('verdict')).toBeNull()
    expect((container.querySelector('#inbox-search') as HTMLInputElement).value).toBe('plataforma')
    act(() => { void router.navigate(-1) })
    await flush()
    expect(search(container).get('search')).toBe('backend')
    expect((container.querySelector('#inbox-search') as HTMLInputElement).value).toBe('backend')
    act(() => { void router.navigate(1) })
    await flush()
    expect(search(container).get('search')).toBe('plataforma')
    expect((container.querySelector('#inbox-search') as HTMLInputElement).value).toBe('plataforma')
    act(() => { void router.navigate(1) })
    await flush()
    expect(search(container).get('verdict')).toBe('RECOMMENDED')
  })

  it('abaixo de xl a mesma tabela vira cartões sem perder a semântica de tabela', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      })),
    )
    stubInbox(1, [])
    const container = renderAt('/inbox')
    await flush()

    // One DOM for every width: the layout is CSS, so there is no second list to announce.
    expect(container.querySelectorAll('table')).toHaveLength(1)
    expect(container.querySelector('article')).toBeNull()
    const table = container.querySelector('table[role="table"]')
    expect(table?.className).toContain('max-xl:block')
    expect(table?.querySelector('thead')?.className).toContain('max-xl:sr-only')
    expect(table?.parentElement?.className).toContain('xl:overflow-x-auto')
  })

  it('expõe cabeçalhos de coluna e linhas da tabela por papel ARIA', async () => {
    stubInbox(2, [], [inboxItem(), inboxItem({ opportunity_id: 'opp-2', title: 'Data Engineer' })])
    const container = renderAt('/inbox')
    await flush()

    const table = container.querySelector('[role="table"]') as HTMLElement
    expect(table).not.toBeNull()
    expect(table.querySelector('caption')?.textContent).toBe('Oportunidades')
    expect(
      [...table.querySelectorAll('[role="columnheader"]')].map((header) => header.textContent),
    ).toEqual(['Vaga', 'Score e decisão', 'Sinais', 'Publicada', 'Ações'])
    const rows = [...table.querySelectorAll('tbody [role="row"]')]
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(row.querySelectorAll('[role="cell"]')).toHaveLength(5)
    }
    expect(table.querySelectorAll('[role="rowgroup"]')).toHaveLength(2)
  })

  it('mostra o score em caixa tabular e, ao lado, o nome do veredito', async () => {
    stubInbox(1, [], [inboxItem({ score: '82', verdict: 'RECOMMENDED' })])
    const container = renderAt('/inbox')
    await flush()

    const cell = container.querySelectorAll('tbody [role="cell"]')[1] as HTMLElement
    expect(cell.textContent).toContain('82.0')
    expect(cell.querySelector('.tabular-nums')?.textContent).toBe('82.0')
    expect(cell.textContent).toContain('Recomendada')
  })

  it('desenha o kicker "Decidir", o título novo e as buscas salvas no cabeçalho', async () => {
    stubInbox(1, [])
    const container = renderAt('/inbox')
    await flush()

    const header = container.querySelector('header') as HTMLElement
    expect(header.querySelector('p')?.textContent).toBe('Decidir')
    expect(header.querySelector('h1')?.textContent).toBe('Quais vagas merecem sua atenção agora?')
    expect(
      [...header.querySelectorAll('button')].some((button) => button.textContent === 'Buscas salvas'),
    ).toBe(true)
  })

  it('explica a leitura do score, fatores desconhecidos, análise semântica e avaliações stale', async () => {
    stubInbox(0, [])
    const container = renderAt('/inbox')
    await flush()

    const guidance = container.querySelector('aside[aria-label="Como interpretar as avaliações"]')
    expect(guidance?.textContent).toContain('regras determinísticas')
    expect(guidance?.textContent).toContain('pedem revisão')
    expect(guidance?.textContent).toContain('consultiva')
    expect(guidance?.textContent).toContain('desatualizados')
  })

  it('distingue o vazio sem dados do vazio por filtro', async () => {
    stubInbox(0, [], [])
    const bare = renderAt('/inbox')
    await flush()
    expect(bare.textContent).toContain('Ainda não há oportunidades para mostrar')
    expect(bare.textContent).not.toContain('Nenhuma oportunidade encontrada com esses filtros.')

    const filtered = renderAt('/inbox?work_mode=REMOTE')
    await flush()
    expect(filtered.textContent).toContain('Nenhuma oportunidade encontrada com esses filtros.')
  })

  it('envia à API os mesmos parâmetros de sempre para os filtros primários e avançados', async () => {
    const urls: string[] = []
    stubInbox(
      1,
      urls,
      [inboxItem()],
    )
    renderAt('/inbox?verdict=RECOMMENDED&work_mode=REMOTE&order=score&minimum_score=60&seniority=SENIOR&search=backend&size=50')
    await flush()

    const inbox = new URL(urls.find((url) => url.includes('/inbox')) as string, 'http://localhost')
    expect(inbox.searchParams.getAll('verdict')).toEqual(['RECOMMENDED'])
    expect(inbox.searchParams.get('work_mode')).toBe('REMOTE')
    expect(inbox.searchParams.get('order')).toBe('score')
    expect(inbox.searchParams.get('minimum_score')).toBe('60')
    expect(inbox.searchParams.get('search')).toBe('backend')
    expect(inbox.searchParams.get('limit')).toBe('50')
  })

  it('envia à API todos os valores repetidos de verdict, seniority e source da URL', async () => {
    const urls: string[] = []
    stubInbox(1, urls, [inboxItem()])
    renderAt(
      '/inbox?seniority=JUNIOR&seniority=MID&verdict=RECOMMENDED&verdict=WATCHLIST&source=src-a&source=src-b',
    )
    await flush()

    const inbox = new URL(urls.find((url) => url.includes('/inbox')) as string, 'http://localhost')
    expect(inbox.searchParams.getAll('seniority')).toEqual(['JUNIOR', 'MID'])
    expect(inbox.searchParams.getAll('verdict')).toEqual(['RECOMMENDED', 'WATCHLIST'])
    expect(inbox.searchParams.getAll('source_definition_id')).toEqual(['src-a', 'src-b'])
  })

  it('pagina pelo Pagination, preserva ?page= e envia a página à API', async () => {
    const urls: string[] = []
    stubInbox(60, urls)
    const container = renderAt('/inbox?page=2')
    await flush()

    expect(urls.some((url) => url.includes('/inbox') && url.includes('offset=25'))).toBe(true)
    expect(container.textContent).toContain('Exibindo 26 a 50 de 60 oportunidades')

    const next = container.querySelector('button[aria-label="Próxima página"]') as HTMLButtonElement
    act(() => next.click())
    await flush()
    expect(search(container).get('page')).toBe('3')

    const first = container.querySelector('button[aria-label="Página 1"]') as HTMLButtonElement
    act(() => first.click())
    await flush()
    expect(search(container).get('page')).toBeNull()
  })

  it('trocar o tamanho da página o coloca na URL e volta para a página 1', async () => {
    const urls: string[] = []
    stubInbox(300, urls)
    const container = renderAt('/inbox?page=3')
    await flush()

    const select = container.querySelector('#inbox-page-size') as HTMLSelectElement
    expect(select.value).toBe('25')
    choose(select, '50')
    await flush()

    expect(search(container).get('size')).toBe('50')
    expect(search(container).get('page')).toBeNull()
    expect(urls.some((url) => url.includes('/inbox') && url.includes('limit=50'))).toBe(
      true,
    )

    choose(container.querySelector('#inbox-page-size') as HTMLSelectElement, '25')
    await flush()
    expect(search(container).get('size')).toBeNull()
  })

  it('mudar um filtro volta para a página 1 e mantém o tamanho', async () => {
    stubInbox(300, [])
    const container = renderAt('/inbox?page=4&size=50')
    await flush()

    choose(container.querySelector('#inbox-work-mode') as HTMLSelectElement, 'REMOTE')
    await flush()

    const params = search(container)
    expect(params.get('work_mode')).toBe('REMOTE')
    expect(params.get('page')).toBeNull()
    expect(params.get('size')).toBe('50')
  })

  it('a Candidatura é um FilterPill e filtra por applied', async () => {
    stubInbox(1, [])
    const container = renderAt('/inbox')
    await flush()

    choose(container.querySelector('#inbox-applied') as HTMLSelectElement, 'true')
    await flush()
    expect(search(container).get('applied')).toBe('true')
  })

  it('concentra filtros secundários no disclosure, informa os ativos e os limpa sem apagar a busca', async () => {
    stubInbox(1, [])
    const container = renderAt(
      '/inbox?search=backend&work_mode=REMOTE&seniority=SENIOR&only_startups=true&page=3',
    )
    await flush()

    const details = container.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(true)
    expect(details.textContent).toContain('Filtros avançados (2 ativos)')
    expect(container.textContent).toContain('3 filtros ativos')
    expect((container.querySelector('#inbox-seniority') as HTMLElement).closest('details')).toBe(
      details,
    )
    expect((container.querySelector('#inbox-applied') as HTMLElement).closest('details')).toBe(
      details,
    )
    const startupLabel = Array.from(container.querySelectorAll('label')).find((candidate) =>
      candidate.textContent?.includes('Só startups'),
    )
    expect(startupLabel?.closest('details')).toBe(details)

    act(() => {
      details.open = false
      details.dispatchEvent(new Event('toggle', { bubbles: true }))
    })
    expect(details.open).toBe(false)

    clickButton(container, 'Limpar filtros')
    await flush()

    const params = search(container)
    expect(params.get('search')).toBe('backend')
    expect(params.get('work_mode')).toBeNull()
    expect(params.get('seniority')).toBeNull()
    expect(params.get('only_startups')).toBeNull()
    expect(params.get('page')).toBeNull()
    expect(container.textContent).toContain('Nenhum filtro ativo')
  })

  it('as buscas salvas ficam num menu: abre, aplica a busca e Esc fecha', async () => {
    stubInbox(1, [])
    const container = renderAt('/inbox')
    await flush()

    const button = Array.from(container.querySelectorAll('button')).find(
      (candidate) => candidate.textContent === 'Buscas salvas',
    ) as HTMLButtonElement
    expect(button.getAttribute('aria-expanded')).toBe('false')
    expect(container.textContent).not.toContain('Backend remoto')

    act(() => button.click())
    await flush()
    expect(button.getAttribute('aria-expanded')).toBe('true')
    expect(container.textContent).toContain('Backend remoto')
    expect(container.textContent).toContain('Salvar esta busca')

    act(() => {
      button.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    })
    expect(button.getAttribute('aria-expanded')).toBe('false')

    act(() => button.click())
    await flush()
    clickButton(container, 'Backend remoto')
    await flush()
    expect(search(container).get('work_mode')).toBe('REMOTE')
    expect(button.getAttribute('aria-expanded')).toBe('false')
  })

  it('limpa o rascunho não submetido quando uma busca salva sem termo é aplicada', async () => {
    stubInbox(1, [])
    const container = renderAt('/inbox')
    await flush()

    typeInto(container.querySelector('#inbox-search') as HTMLInputElement, 'rascunho')
    const menu = Array.from(container.querySelectorAll('button')).find(
      (candidate) => candidate.textContent === 'Buscas salvas',
    ) as HTMLButtonElement
    act(() => menu.click())
    await flush()
    clickButton(container, 'Backend remoto')
    await flush()

    expect(search(container).get('search')).toBeNull()
    expect(search(container).get('work_mode')).toBe('REMOTE')
    expect((container.querySelector('#inbox-search') as HTMLInputElement).value).toBe('')
  })
  it('mostra Relevância e desabilita a ordenação enquanto há texto na busca, preservando order', async () => {
    stubInbox(1, [])
    const container = renderAt('/inbox?search=react&order=score')
    await flush()

    const select = container.querySelector('#inbox-order') as HTMLSelectElement
    expect(select.disabled).toBe(true)
    expect(select.selectedOptions[0].textContent).toBe('Relevância')
    const description = document.getElementById(select.getAttribute('aria-describedby') ?? '')
    expect(description?.textContent).toBe(
      'Com texto na busca, os resultados são ordenados por relevância',
    )
    expect(search(container).get('order')).toBe('score')
  })

  it('mantém a ordenação habilitada e com o valor da URL sem texto na busca', async () => {
    stubInbox(1, [])
    const container = renderAt('/inbox?order=score')
    await flush()

    const select = container.querySelector('#inbox-order') as HTMLSelectElement
    expect(select.disabled).toBe(false)
    expect(select.selectedOptions[0].textContent).toBe('Maior score')
    expect(select.hasAttribute('aria-describedby')).toBe(false)
  })
})

describe('InboxPage salary unit (D1)', () => {
  function stub(urls: string[], items: unknown[] = [inboxItem()]) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        urls.push(url)
        if (url.includes('/inbox')) {
          return new Response(
            JSON.stringify({ items, total: items.length, offset: 0, limit: 25, order: 'priority', off_filter_count: 0 }),
            { status: 200 },
          )
        }
        return new Response(JSON.stringify([]), { status: 200 })
      }),
    )
  }

  function Probe() {
    const location = useLocation()
    return <output data-testid="location">{location.search}</output>
  }

  function renderAt(path: string): HTMLElement {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <InboxPage />
          <Probe />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  function search(container: HTMLElement): URLSearchParams {
    return new URLSearchParams(container.querySelector('[data-testid="location"]')?.textContent ?? '')
  }

  function choose(select: HTMLSelectElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    act(() => {
      setter?.call(select, value)
      select.dispatchEvent(new Event('change', { bubbles: true }))
    })
  }

  function lastInbox(urls: string[]): URL {
    const inbox = urls.filter((url) => url.includes('/inbox'))
    return new URL(inbox[inbox.length - 1], 'http://localhost')
  }

  function salaryMinInput(container: HTMLElement): HTMLInputElement {
    const label = Array.from(container.querySelectorAll('label')).find((candidate) =>
      candidate.textContent?.includes('Remuneração mínima'),
    )
    return (label?.querySelector('input') ??
      document.getElementById(label?.getAttribute('for') ?? '')) as HTMLInputElement
  }

  it('envia BRL e MONTH por padrão quando há salário mínimo', async () => {
    const urls: string[] = []
    stub(urls)
    const container = renderAt('/inbox')
    await flush()
    typeInto(salaryMinInput(container), '5000')
    await flush()

    const inbox = lastInbox(urls)
    expect(inbox.searchParams.get('salary_min')).toBe('5000')
    expect(inbox.searchParams.get('salary_currency')).toBe('BRL')
    expect(inbox.searchParams.get('salary_period')).toBe('MONTH')
  })

  it('trocar moeda e período altera a API e a URL', async () => {
    const urls: string[] = []
    stub(urls)
    const container = renderAt('/inbox?salary_min=100')
    await flush()
    choose(container.querySelector('#inbox-salary-currency') as HTMLSelectElement, 'USD')
    await flush()
    choose(container.querySelector('#inbox-salary-period') as HTMLSelectElement, 'YEAR')
    await flush()

    const inbox = lastInbox(urls)
    expect(inbox.searchParams.get('salary_currency')).toBe('USD')
    expect(inbox.searchParams.get('salary_period')).toBe('YEAR')
    expect(search(container).get('salary_currency')).toBe('USD')
    expect(search(container).get('salary_period')).toBe('YEAR')
  })

  it('sem valor salarial não envia moeda nem período e desabilita os selects', async () => {
    const urls: string[] = []
    stub(urls)
    const container = renderAt('/inbox?salary_currency=USD&salary_period=YEAR')
    await flush()

    const inbox = lastInbox(urls)
    expect(inbox.searchParams.has('salary_currency')).toBe(false)
    expect(inbox.searchParams.has('salary_period')).toBe(false)
    const currency = container.querySelector('#inbox-salary-currency') as HTMLSelectElement
    expect(currency.disabled).toBe(true)
    expect(currency.value).toBe('USD')
    expect((container.querySelector('#inbox-salary-period') as HTMLSelectElement).disabled).toBe(true)
    expect(container.textContent).toContain('Compara só vagas na mesma moeda e período.')
  })

  it('mostra o selo só para salary_match unknown', async () => {
    const urls: string[] = []
    stub(urls, [
      inboxItem({ opportunity_id: 'a', title: 'Vaga A', salary_match: 'unknown' }),
      inboxItem({ opportunity_id: 'b', title: 'Vaga B', salary_match: 'matched' }),
    ])
    const container = renderAt('/inbox?salary_min=100')
    await flush()

    const rows = Array.from(container.querySelectorAll('tr'))
    const rowA = rows.find((row) => row.textContent?.includes('Vaga A'))
    const rowB = rows.find((row) => row.textContent?.includes('Vaga B'))
    expect(rowA?.textContent).toContain('remuneração não informada')
    expect(rowB?.textContent).not.toContain('remuneração não informada')
  })

  it('a busca salva leva moeda e período quando há faixa salarial', () => {
    expect(filtersFromParams(new URLSearchParams('salary_min=100'))).toEqual({
      salary_min: '100',
      salary_currency: 'BRL',
      salary_period: 'MONTH',
    })
    expect(
      filtersFromParams(new URLSearchParams('salary_max=9&salary_currency=EUR&salary_period=HOUR')),
    ).toEqual({ salary_max: '9', salary_currency: 'EUR', salary_period: 'HOUR' })
    expect(filtersFromParams(new URLSearchParams('salary_currency=USD&work_mode=REMOTE'))).toEqual({
      work_mode: 'REMOTE',
    })
  })
})

installTestAuth()
