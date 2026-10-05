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

function company(index: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `company-${index}`,
    name: `Empresa ${index}`,
    domain: `empresa${index}.com`,
    priority: 'high',
    status: 'active',
    verification_state: 'careers_confirmed',
    sources: [],
    ...overrides,
  }
}

/** Serves `/companies` from `total` synthetic companies, honouring page and page_size. */
function stubCompanies(total: number, overrides: Record<string, unknown> = {}) {
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
        company(start + i + 1, overrides),
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
    expect(chips).toEqual(['Alta', 'Ativa', 'Carreiras confirmadas'])
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

  it('filtra somente os resultados exibidos na página e deixa esse escopo explícito', async () => {
    const urls = stubCompanies(3)
    const container = renderPage(<CompaniesPage />)
    await flush()

    const select = container.querySelector<HTMLSelectElement>('#company-priority')
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    act(() => {
      setter?.call(select, 'low')
      select?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()

    expect(container.querySelectorAll('tbody tr')).toHaveLength(0)
    expect(container.textContent).toContain('Nenhuma empresa desta página corresponde aos filtros selecionados.')
    expect(container.textContent).toContain('0 de 3 exibidas nesta página após os filtros.')
    expect(urls).toHaveLength(1)
  })

  it('limpa os três filtros locais e restaura os resultados da página atual', async () => {
    stubCompanies(3)
    const container = renderPage(<CompaniesPage />)
    await flush()

    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    const priority = container.querySelector<HTMLSelectElement>('#company-priority')
    const status = container.querySelector<HTMLSelectElement>('#company-status')
    const verification = container.querySelector<HTMLSelectElement>('#company-verification')
    act(() => {
      setter?.call(priority, 'low')
      priority?.dispatchEvent(new Event('change', { bubbles: true }))
      setter?.call(status, 'backlog')
      status?.dispatchEvent(new Event('change', { bubbles: true }))
      setter?.call(verification, 'ats_identified')
      verification?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()

    const clear = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Limpar filtros')
    expect(clear).toBeDefined()
    act(() => clear?.click())
    await flush()

    expect(priority?.value).toBe('')
    expect(status?.value).toBe('')
    expect(verification?.value).toBe('')
    expect(container.querySelectorAll('tbody tr')).toHaveLength(3)
    expect(container.textContent).not.toContain('após os filtros.')
    expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Limpar filtros')).toBe(false)
  })

  it('traduz e filtra os estados realmente usados no catálogo e nas fontes', async () => {
    stubCompanies(2, {
      priority: 'normal',
      status: 'backlog',
      verification_state: 'ats_identified',
      sources: [{ name: 'Greenhouse', status: 'careers_confirmed' }],
    })

    const container = renderPage(<CompaniesPage />)
    await flush()

    const rows = container.querySelectorAll('tbody tr')
    expect(rows[0].textContent).toContain('Normal')
    expect(rows[0].textContent).toContain('Em fila')
    expect(rows[0].textContent).toContain('ATS identificado')
    expect(rows[0].textContent).toContain('Carreiras confirmadas')

    const status = container.querySelector<HTMLSelectElement>('#company-status')
    const verification = container.querySelector<HTMLSelectElement>('#company-verification')
    expect([...(status?.options ?? [])].map((option) => option.value)).toContain('backlog')
    expect([...(verification?.options ?? [])].map((option) => option.value)).toEqual([
      '',
      'api_json_confirmed',
      'ats_identified',
      'careers_confirmed',
      'research_recorded',
      'backlog',
      'unverified',
    ])

    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    act(() => {
      setter?.call(verification, 'ats_identified')
      verification?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()
    expect(container.querySelectorAll('tbody tr')).toHaveLength(2)
  })

  it('mostra os estados de verificação provenientes da API', async () => {
    stubCompanies(1, { verification_state: 'api_json_confirmed' })
    const container = renderPage(<CompaniesPage />)
    await flush()

    expect(container.textContent).toContain('API JSON confirmada')

    const verification = container.querySelector<HTMLSelectElement>('#company-verification')
    const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set
    act(() => {
      setter?.call(verification, 'unverified')
      verification?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await flush()
    expect(container.querySelectorAll('tbody tr')).toHaveLength(0)
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
