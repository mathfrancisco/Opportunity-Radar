import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { SavedSearchesWithNews } from './OverviewPage'

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
