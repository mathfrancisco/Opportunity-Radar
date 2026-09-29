import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { CompaniesPage } from './CompaniesPage'

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

function company(index: number) {
  return {
    id: `company-${index}`,
    name: `Empresa ${index}`,
    domain: `empresa${index}.com`,
    priority: 'high',
    status: 'active',
    verification_state: 'VERIFIED',
    sources: [],
  }
}

/** Serves `/companies` from `total` synthetic companies, honouring page and page_size. */
function stubCompanies(total: number) {
  const urls: URL[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      const url = new URL(String(input), 'http://localhost')
      urls.push(url)
      const page = Number(url.searchParams.get('page') ?? '1')
      const size = Number(url.searchParams.get('page_size') ?? '25')
      const start = (page - 1) * size
      const items = Array.from({ length: Math.max(0, Math.min(size, total - start)) }, (_, i) =>
        company(start + i + 1),
      )
      return new Response(JSON.stringify({ items, page, page_size: size, total }), {
        status: 200,
      })
    }),
  )
  return urls
}

function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  act(() => {
    setter?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

describe('CompaniesPage', () => {
  it('lista as empresas num DataTable com chips e fontes em cinza', async () => {
    stubCompanies(3)

    const container = renderPage(<CompaniesPage />)
    await flush()

    const rows = container.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(3)
    expect(rows[0].querySelector('a')?.getAttribute('href')).toBe('/companies/company-1')
    const chips = [...rows[0].querySelectorAll('span.rounded-chip')].map((chip) => chip.textContent)
    expect(chips).toEqual(['high', 'active', 'VERIFIED'])
    expect(rows[0].textContent).toContain('Nenhuma fonte cadastrada')
    expect(container.textContent).toContain('3 empresas encontradas.')
  })

  it('usa SearchInput com a mesma busca por nome ou domínio', async () => {
    const urls = stubCompanies(3)

    const container = renderPage(<CompaniesPage />)
    await flush()

    const input = container.querySelector<HTMLInputElement>('#company-search')
    expect(input?.type).toBe('search')
    typeInto(input as HTMLInputElement, ' acme ')
    act(() => container.querySelector<HTMLFormElement>('form[role="search"]')?.requestSubmit())
    await flush()

    expect(urls.at(-1)?.searchParams.get('q')).toBe('acme')
    expect(urls.at(-1)?.searchParams.get('page')).toBe('1')
  })

  it('pagina: mostra o intervalo, troca de página e pede page/page_size à API', async () => {
    const urls = stubCompanies(60)

    const container = renderPage(<CompaniesPage />)
    await flush()

    expect(container.textContent).toContain('Exibindo 1 a 25 de 60 empresas')
    expect(container.querySelectorAll('tbody tr')).toHaveLength(25)

    act(() => container.querySelector<HTMLButtonElement>('button[aria-label="Página 2"]')?.click())
    await flush()

    expect(urls.at(-1)?.searchParams.get('page')).toBe('2')
    expect(container.textContent).toContain('Exibindo 26 a 50 de 60 empresas')
    expect(
      container.querySelector('button[aria-label="Página 2"]')?.getAttribute('aria-current'),
    ).toBe('page')
  })

  it('trocar o tamanho da página volta para a primeira e respeita o máximo de 100', async () => {
    const urls = stubCompanies(60)

    const container = renderPage(<CompaniesPage />)
    await flush()
    act(() => container.querySelector<HTMLButtonElement>('button[aria-label="Página 2"]')?.click())
    await flush()

    const select = container.querySelector<HTMLSelectElement>('#companies-page-size')
    expect([...(select?.options ?? [])].map((option) => option.value)).toEqual([
      '10',
      '25',
      '50',
      '100',
    ])
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    act(() => {
      setter?.call(select, '10')
      select?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()

    expect(urls.at(-1)?.searchParams.get('page')).toBe('1')
    expect(urls.at(-1)?.searchParams.get('page_size')).toBe('10')
    expect(container.querySelectorAll('tbody tr')).toHaveLength(10)
  })

  it('abaixo de md mostra cartões, sem tabela, com a mesma paginação', async () => {
    stubCompanies(30)
    vi.stubGlobal(
      'matchMedia',
      vi.fn(() => ({
        matches: false,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      })),
    )

    const container = renderPage(<CompaniesPage />)
    await flush()

    expect(container.querySelector('table')).toBeNull()
    expect(container.querySelectorAll('article')).toHaveLength(25)
    expect(container.textContent).toContain('Exibindo 1 a 25 de 30 empresas')
  })
})
