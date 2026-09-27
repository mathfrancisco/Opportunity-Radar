import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { type SavedSearchFilters } from '../features/saved-searches/api'
import { SaveSearchForm, SavedSearches } from './InboxPage'

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
