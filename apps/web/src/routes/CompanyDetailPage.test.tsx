import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { CompanyDetailPage } from './CompanyDetailPage'

afterEach(() => vi.unstubAllGlobals())

async function flush(times = 4) {
  for (let index = 0; index < times; index += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderWithProviders(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>)
}

describe('CompanyDetailPage', () => {
  it('mostra o kicker do catálogo e associa rótulos e erros ao formulário de ATS', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.includes('/inbox?')) {
          return new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 5 }))
        }
        if (url.endsWith('/companies/company-1')) {
          return new Response(JSON.stringify({
            id: 'company-1',
            name: 'Acme',
            domain: 'acme.example',
            priority: 'high',
            status: 'active',
            verification_state: 'ats_identified',
            aliases: [],
            sources: [],
            version: 1,
          }))
        }
        return new Response('{}', { status: 404 })
      }),
    )

    const container = renderWithProviders(
      <MemoryRouter initialEntries={['/companies/company-1']}>
        <Routes>
          <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
    await flush(6)

    expect(container.querySelector('header p')?.textContent).toBe('Catálogo local')
    const registerButton = [...container.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Registrar ATS',
    )
    act(() => registerButton?.click())

    const form = container.querySelector<HTMLFormElement>('form')
    expect(form).not.toBeNull()
    const controls = [...(form?.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
      'input, select, textarea',
    ) ?? [])]
    expect(controls.map((control) => document.getElementById(control.getAttribute('aria-labelledby') ?? '')?.textContent))
      .toEqual(['ATS', 'Chave no ATS', 'Endereço do board', 'Nota de evidência'])

    act(() => form?.requestSubmit())
    for (const index of [1, 2, 3]) {
      expect(controls[index].getAttribute('aria-invalid')).toBe('true')
      const descriptionIds = (controls[index].getAttribute('aria-describedby') ?? '').split(' ')
      expect(descriptionIds.some((id) => document.getElementById(id)?.classList.contains('text-danger-ink')))
        .toBe(true)
    }
  })

  it('uses readable source states and keeps source actions reachable from local navigation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.includes('/inbox?')) {
          return new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 5 }))
        }
        if (url.endsWith('/companies/company-1')) {
          return new Response(JSON.stringify({
            id: 'company-1',
            name: 'Acme',
            domain: 'acme.example',
            priority: 'high',
            status: 'backlog',
            verification_state: 'ats_identified',
            aliases: [],
            sources: [{
              id: 'source-1',
              name: 'Acme careers',
              url: 'https://acme.example/careers',
              status: 'careers_confirmed',
              external_key: null,
              verification_method: 'discovery',
              evidence: null,
              last_verified_at: null,
              version: 1,
              revisions: [],
              proposal: null,
            }],
            version: 1,
          }))
        }
        return new Response('{}', { status: 404 })
      }),
    )

    const container = renderWithProviders(
      <MemoryRouter initialEntries={['/companies/company-1']}>
        <Routes>
          <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
    await flush(6)

    const navigation = container.querySelector('nav[aria-label="Navegar nesta empresa"]')
    expect(navigation?.querySelector('a[href="#resumo"]')?.textContent).toBe('Resumo')
    expect(navigation?.querySelector('a[href="#fontes"]')?.textContent).toBe('Fontes')
    expect(navigation?.querySelector('a[href="#vagas"]')?.textContent).toBe('Vagas')
    expect(container.querySelector('#fontes')).not.toBeNull()
    expect(container.textContent).toContain('ATS identificado')
    expect(container.textContent).toContain('Carreiras confirmadas')
    expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Propor fonte a partir do ATS')).toBe(true)
    expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Registrar ATS')).toBe(true)
  })
})
