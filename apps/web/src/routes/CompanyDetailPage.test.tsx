import { installTestAuth } from '../test/auth'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render, visibleTextOutsideDetails } from '../components/testing'
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
              revisions: [{
                version: 2,
                changed_at: '2040-01-02T00:00:00Z',
                changes: {
                  homologation_audit: {
                    from: null,
                    to: { status: 'reviewed', api_token: 'private-value', detail: { internal: true } },
                  },
                },
                evidence_note: 'Revisão administrativa',
              }],
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
    expect(container.textContent).toContain('homologation_audit: status: reviewed')
    expect(container.textContent).toContain('valor estruturado')
    expect(container.textContent).not.toContain('private-value')
    expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Propor fonte a partir do ATS')).toBe(true)
    expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Registrar ATS')).toBe(true)
  })

  function stubDetail(options: { inbox?: 'ok' | 'fail' | 'empty' | 'pending'; company?: 'ok' | 'fail' | 'pending' } = {}) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.includes('/inbox?')) {
          if (options.inbox === 'pending') return new Promise<Response>(() => {})
          if (options.inbox === 'fail') return new Response('{}', { status: 500 })
          const items = options.inbox === 'empty' ? [] : [
            { opportunity_id: 'op-1', title: 'Engenheira de dados', work_mode: 'REMOTE', verdict: 'HIGH_PRIORITY', score: '88.0' },
            { opportunity_id: 'op-2', title: 'Analista', work_mode: 'ONSITE', verdict: 'SOME_NEW_VERDICT', score: '40.0' },
            { opportunity_id: 'op-3', title: 'Dev', work_mode: 'REMOTE', verdict: null, score: null },
          ]
          return new Response(JSON.stringify({ items, total: items.length, offset: 0, limit: 5 }))
        }
        if (url.endsWith('/companies/company-1')) {
          if (options.company === 'pending') return new Promise<Response>(() => {})
          if (options.company === 'fail') return new Response('{}', { status: 500 })
          return new Response(JSON.stringify({
            id: 'company-1',
            name: 'Acme',
            domain: 'acme.example',
            priority: 'URGENT_REVIEW',
            status: 'active',
            verification_state: 'NEEDS_HUMAN_CHECK',
            aliases: [],
            sources: [{
              id: 'source-1',
              name: 'Acme careers',
              url: 'https://acme.example/careers',
              status: 'NOT_CONFIRMED_YET',
              external_key: 'acme-key',
              verification_method: 'DISCOVERY_SCAN',
              evidence: null,
              last_verified_at: null,
              version: 1,
              revisions: [],
              proposal: { source_id: 'p1', source_type: 'GREENHOUSE_BOARD', external_key: 'acme-key', enabled: false, evidence_status: 'NOT_CONFIRMED', version: 2 },
            }],
            version: 1,
          }))
        }
        return new Response('{}', { status: 404 })
      }),
    )
    return renderWithProviders(
      <MemoryRouter initialEntries={['/companies/company-1']}>
        <Routes>
          <Route path="/companies/:companyId" element={<CompanyDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('mostra o esqueleto enquanto a empresa carrega', async () => {
    const container = stubDetail({ company: 'pending' })
    await flush(2)

    expect(container.querySelector('[aria-busy="true"]')?.textContent).toContain('Carregando empresa…')
  })

  it('no erro da empresa, diz o que continua valendo', async () => {
    const container = stubDetail({ company: 'fail' })
    await flush(6)

    const alert = container.querySelector('[role="alert"]')
    expect(alert?.textContent).toContain('outras empresas continuam disponíveis')
    expect(alert?.querySelector('button')?.textContent).toBe('Tentar novamente')
  })

  it('sem vagas, explica quando elas aparecem', async () => {
    const container = stubDetail({ inbox: 'empty' })
    await flush(6)

    expect(container.textContent).toContain('Nenhuma vaga desta empresa até agora.')
  })

  it('carrega vagas com esqueleto', async () => {
    const container = stubDetail({ inbox: 'pending' })
    await flush(6)

    expect(container.textContent).toContain('Carregando vagas…')
    expect(container.querySelectorAll('[aria-busy="true"]')).toHaveLength(1)
  })

  it('parcial: se as vagas falham, a empresa continua na tela com uma nota neutra', async () => {
    const container = stubDetail({ inbox: 'fail' })
    await flush(6)

    expect(container.querySelector('h1')?.textContent).toBe('Acme')
    expect(container.querySelector('#fontes')?.textContent).toContain('Acme careers')
    const notes = [...container.querySelectorAll('[role="status"]')].map((node) => node.textContent)
    expect(notes.some((text) => text?.includes('Não foi possível carregar as vagas agora.'))).toBe(true)
    expect(container.querySelector('[role="alert"]')).toBeNull()
  })

  it('traduz o veredito com a mesma etiqueta da Inbox e não mostra código técnico', async () => {
    const container = stubDetail()
    await flush(6)

    const rows = [...container.querySelectorAll('#vagas tbody tr')]
    expect(rows[0].textContent).toContain('Alta prioridade')
    expect(rows[0].textContent).toContain('Remoto')
    expect(rows[0].querySelector('span.rounded-chip')?.className).toContain('bg-nugget-surface')
    expect(rows[1].textContent).toContain('Em revisão')
    expect(rows[2].textContent).toContain('Não avaliada')

    const text = visibleTextOutsideDetails(container)
    expect(text).not.toMatch(/[A-Z]{3,}_[A-Z_]+/)
    expect(container.querySelector('details')?.textContent).toContain('Detalhe técnico')
    expect(container.textContent).toContain('NOT_CONFIRMED')
  })
})

installTestAuth()
