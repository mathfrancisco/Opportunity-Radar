import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { type SavedSearchFilters } from '../features/saved-searches/api'
import { InboxPage, SaveSearchForm, SavedSearches } from './InboxPage'

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
      label.textContent?.includes('Mostrar só vagas dos últimos 14 dias'),
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
      label.textContent?.includes('Mostrar só vagas dos últimos 14 dias'),
    )
    const checkbox = toggle?.querySelector('input') as HTMLInputElement
    act(() => checkbox.click())
    await flush()

    expect(calledUrls.some((url) => url.includes('/inbox') && url.includes('only_recent=false'))).toBe(
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
})
