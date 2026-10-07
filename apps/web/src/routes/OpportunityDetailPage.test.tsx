import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { type OpportunityDetail } from '../features/opportunities/api'
import {
  DuplicateCandidates,
  OpportunityDescription,
  OpportunityDetailPage,
  SiblingLocations,
} from './OpportunityDetailPage'

afterEach(() => vi.unstubAllGlobals())

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderWithProviders(element: ReactElement, withRouter = true): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      {withRouter ? <MemoryRouter>{element}</MemoryRouter> : element}
    </QueryClientProvider>,
  )
}

function opportunity(overrides: Partial<OpportunityDetail> = {}): OpportunityDetail {
  return {
    id: 'opportunity-1',
    fingerprint: 'fp-1',
    fingerprintVersion: 'v1',
    title: 'Backend Engineer',
    companyId: null,
    companyName: 'Acme',
    location: 'São Paulo',
    workMode: 'REMOTE',
    seniority: 'SENIOR',
    contractType: 'FULL_TIME',
    description: null,
    lifecycleStatus: 'ACTIVE',
    publishedAt: '2026-09-10T00:00:00Z',
    recencyEffectiveDate: '2026-09-10T00:00:00Z',
    recencyBasis: 'published',
    createdAt: '2026-09-05T00:00:00Z',
    version: 1,
    compensations: [],
    skills: [],
    occurrences: [],
    normalizationResults: [],
    siblingLocations: [],
    relevanceMark: null,
    ...overrides,
  }
}

function candidate(overrides: Record<string, unknown> = {}) {
  return {
    id: 'candidate-1',
    opportunity_id: 'opportunity-1',
    duplicate_opportunity_id: 'opportunity-2',
    survivor_opportunity_id: 'opportunity-1',
    absorbed_opportunity_id: 'opportunity-2',
    rule: 'title_location_window',
    score: null,
    status: 'PENDING',
    decided_by: null,
    decided_at: null,
    created_at: '2026-09-11T00:00:00Z',
    ...overrides,
  }
}

/** Routes requests by method and path, never a real network call. */
function stubFetch(options: {
  candidates?: ReturnType<typeof candidate>[]
  otherOpportunity?: Partial<OpportunityDetail> & { id: string }
  onConfirm?: (body: unknown) => void
  onReject?: (body: unknown) => void
}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/duplicate-candidates') && (!init || init.method === undefined)) {
        return new Response(
          JSON.stringify({ items: options.candidates ?? [] }),
          { status: 200 },
        )
      }
      if (url.endsWith('/confirm')) {
        options.onConfirm?.(init?.body ? JSON.parse(String(init.body)) : null)
        return new Response(
          JSON.stringify(candidate({ status: 'CONFIRMED', decided_by: 'web-operator' })),
          { status: 200 },
        )
      }
      if (url.endsWith('/reject')) {
        options.onReject?.(init?.body ? JSON.parse(String(init.body)) : null)
        return new Response(
          JSON.stringify(candidate({ status: 'REJECTED', decided_by: 'web-operator' })),
          { status: 200 },
        )
      }
      if (options.otherOpportunity && url.endsWith(`/opportunities/${options.otherOpportunity.id}`)) {
        const other = opportunity(options.otherOpportunity)
        return new Response(
          JSON.stringify({
            id: other.id,
            fingerprint: other.fingerprint,
            fingerprint_version: other.fingerprintVersion,
            title: other.title,
            company_id: other.companyId,
            company_name: other.companyName,
            location: other.location,
            work_mode: other.workMode,
            seniority: other.seniority,
            contract_type: other.contractType,
            description: other.description,
            lifecycle_status: other.lifecycleStatus,
            published_at: other.publishedAt,
            created_at: other.createdAt,
            version: other.version,
            compensations: [],
            skills: [],
            occurrences: [],
            normalization_results: [],
            relevance_mark: null,
          }),
          { status: 200 },
        )
      }
      return new Response('{}', { status: 404 })
    }),
  )
}

describe('DuplicateCandidates', () => {
  it('não mostra nada quando não há candidato pendente', async () => {
    stubFetch({ candidates: [] })

    const container = renderWithProviders(
      <DuplicateCandidates opportunity={opportunity()} />,
    )
    await flush()

    expect(container.textContent).toContain('Nenhum candidato a duplicata pendente')
  })

  it('ignora candidatos já confirmados ou recusados', async () => {
    stubFetch({
      candidates: [
        candidate({ id: 'resolved-1', status: 'CONFIRMED' }),
        candidate({ id: 'resolved-2', status: 'REJECTED' }),
      ],
    })

    const container = renderWithProviders(
      <DuplicateCandidates opportunity={opportunity()} />,
    )
    await flush()

    expect(container.textContent).toContain('Nenhum candidato a duplicata pendente')
  })

  it('mostra as duas vagas lado a lado com as diferenças destacadas', async () => {
    stubFetch({
      candidates: [candidate()],
      otherOpportunity: {
        id: 'opportunity-2',
        title: 'Backend Engineer II',
        createdAt: '2026-09-06T00:00:00Z',
      },
    })

    const container = renderWithProviders(
      <DuplicateCandidates opportunity={opportunity()} />,
    )
    await flush()
    await flush()

    expect(container.textContent).toContain('Backend Engineer')
    expect(container.textContent).toContain('Backend Engineer II')
    expect(container.textContent).toContain('Ficaria como sobrevivente')
    expect(container.textContent).toContain('Seria absorvida')
    expect(
      Array.from(container.querySelectorAll('button')).some(
        (button) => button.textContent === 'É a mesma vaga',
      ),
    ).toBe(true)
    expect(
      Array.from(container.querySelectorAll('button')).some(
        (button) => button.textContent === 'São vagas diferentes',
      ),
    ).toBe(true)
  })

  it('confirmar envia a versão da mais antiga como sobrevivente', async () => {
    let confirmedBody: unknown = null
    stubFetch({
      candidates: [candidate()],
      otherOpportunity: {
        id: 'opportunity-2',
        title: 'Backend Engineer II',
        // Newer than the current opportunity (createdAt 2026-09-05), so the current
        // opportunity stays the survivor.
        createdAt: '2026-09-06T00:00:00Z',
        version: 4,
      },
      onConfirm: (body) => {
        confirmedBody = body
      },
    })

    const container = renderWithProviders(
      <DuplicateCandidates opportunity={opportunity({ version: 2 })} />,
    )
    await flush()
    await flush()

    const confirmButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'É a mesma vaga',
    )
    expect(confirmButton).toBeDefined()
    act(() => confirmButton?.click())
    await flush()

    expect(confirmedBody).toEqual({
      expected_version_survivor: 2,
      expected_version_absorbed: 4,
      decided_by: 'web-operator',
    })
  })

  it('empate mantém o menor id como sobrevivente mesmo na página de maior id', async () => {
    let confirmedBody: unknown = null
    stubFetch({
      candidates: [candidate()],
      otherOpportunity: {
        id: 'opportunity-1',
        title: 'Backend Engineer menor id',
        createdAt: '2026-09-05T00:00:00Z',
        version: 3,
      },
      onConfirm: (body) => {
        confirmedBody = body
      },
    })

    const container = renderWithProviders(
      <DuplicateCandidates
        opportunity={opportunity({
          id: 'opportunity-2',
          createdAt: '2026-09-05T00:00:00Z',
          version: 7,
        })}
      />,
    )
    await flush()
    await flush()

    const survivorLabel = Array.from(container.querySelectorAll('p')).find(
      (paragraph) => paragraph.textContent === 'Ficaria como sobrevivente',
    )
    expect(survivorLabel?.parentElement?.querySelector('a')?.getAttribute('href')).toBe(
      '/opportunities/opportunity-1',
    )

    const confirmButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'É a mesma vaga',
    )
    act(() => confirmButton?.click())
    await flush()

    expect(confirmedBody).toEqual({
      expected_version_survivor: 3,
      expected_version_absorbed: 7,
      decided_by: 'web-operator',
    })
  })

  it('recusar grava o par como diferente', async () => {
    let rejectedBody: unknown = null
    stubFetch({
      candidates: [candidate()],
      otherOpportunity: { id: 'opportunity-2', title: 'Backend Engineer II' },
      onReject: (body) => {
        rejectedBody = body
      },
    })

    const container = renderWithProviders(
      <DuplicateCandidates opportunity={opportunity()} />,
    )
    await flush()
    await flush()

    const rejectButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === 'São vagas diferentes',
    )
    expect(rejectButton).toBeDefined()
    act(() => rejectButton?.click())
    await flush()

    expect(rejectedBody).toEqual({ decided_by: 'web-operator' })
  })
})

describe('SiblingLocations (F48-10)', () => {
  it('lists the other cities with links to each opportunity', () => {
    const container = renderWithProviders(
      <SiblingLocations
        opportunity={opportunity({
          siblingLocations: [
            { opportunityId: 'opp-b', location: 'Recife', sourceUrl: 'https://jobs.example/b' },
            { opportunityId: 'opp-c', location: null, sourceUrl: null },
          ],
        })}
      />,
    )
    const links = Array.from(container.querySelectorAll('a')).map((a) => [
      a.textContent,
      a.getAttribute('href'),
    ])
    expect(links).toEqual([
      ['Recife', '/opportunities/opp-b'],
      ['vaga original', 'https://jobs.example/b'],
      ['Local não informado', '/opportunities/opp-c'],
    ])
  })

  it('renders nothing without siblings', () => {
    const container = renderWithProviders(<SiblingLocations opportunity={opportunity()} />)
    expect(container.querySelector('[data-testid="sibling-locations"]')).toBeNull()
  })
})

describe('OpportunityDescription', () => {
  it('converts job-board HTML into safe, readable text with paragraph breaks', () => {
    const container = renderWithProviders(
      <OpportunityDescription
        description={'<p>Build <strong>reliable</strong> systems.</p><p>Apply with CV.<br>Remote &amp; flexible.</p><script>window.executed = true</script>'}
      />,
      false,
    )

    const description = container.querySelector('[data-testid="opportunity-description"]')
    expect(description?.textContent).toBe(
      'Build reliable systems.\n\nApply with CV.\nRemote & flexible.',
    )
    expect(description?.querySelector('script')).toBeNull()
  })
})

describe('OpportunityDetailPage', () => {
  it('keeps the decision and application actions reachable from the local section navigation', async () => {
    const detail = opportunity()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.includes('/duplicate-candidates')) return new Response(JSON.stringify({ items: [] }))
        if (url.includes('/matches?')) return new Response(JSON.stringify({ items: [] }))
        if (url.includes('/applications?')) {
          return new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 1 }))
        }
        if (url.endsWith('/opportunities/opportunity-1')) {
          return new Response(JSON.stringify({
            id: detail.id,
            fingerprint: detail.fingerprint,
            fingerprint_version: detail.fingerprintVersion,
            title: detail.title,
            company_id: detail.companyId,
            company_name: detail.companyName,
            location: detail.location,
            work_mode: detail.workMode,
            seniority: detail.seniority,
            contract_type: detail.contractType,
            description: detail.description,
            lifecycle_status: detail.lifecycleStatus,
            published_at: detail.publishedAt,
            recency_effective_date: detail.recencyEffectiveDate,
            recency_basis: detail.recencyBasis,
            created_at: detail.createdAt,
            version: detail.version,
            compensations: [],
            skills: [],
            occurrences: [],
            normalization_results: [],
            sibling_locations: [],
            relevance_mark: null,
          }))
        }
        return new Response('{}', { status: 404 })
      }),
    )

    const container = renderWithProviders(
      <MemoryRouter initialEntries={['/opportunities/opportunity-1']}>
        <Routes>
          <Route path="/opportunities/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
      false,
    )
    await flush(6)

    const navigation = container.querySelector('nav[aria-label="Navegar nesta oportunidade"]')
    expect(navigation?.querySelector('a[href="#resumo"]')?.textContent).toBe('Resumo')
    expect(navigation?.querySelector('a[href="#decisao"]')?.textContent).toBe('Decisão')
    expect(navigation?.querySelector('a[href="#candidatura"]')?.textContent).toBe('Candidatura')
    expect(container.querySelector('#decisao')).not.toBeNull()
    expect(container.querySelector('#candidatura')).not.toBeNull()
    expect(container.textContent).toContain('Remoto')
    expect(container.textContent).toContain('Tempo integral')
    expect(Array.from(container.querySelectorAll('button')).some((button) => button.textContent === 'Registrar interesse')).toBe(true)
  })
})

describe('OpportunityDetailPage composition (SPEC 54)', () => {
  const assessmentPayload = {
    id: 'assessment-1',
    opportunity_id: 'opportunity-1',
    opportunity_version: 1,
    profile_version_id: 'profile-version-1',
    input_hash: 'a'.repeat(64),
    rules_version: 'matching-v1',
    taxonomy_version: 'skills-v1',
    eligibility: 'ELIGIBLE',
    eligibility_details: [],
    status: 'COMPLETED',
    verdict: 'RECOMMENDED',
    score: '82.0000',
    confidence: '0.700',
    assessed_at: '2026-09-17T12:00:00Z',
    created_at: '2026-09-17T12:00:00Z',
    factors: [],
    analysis: null,
  }

  async function renderDetail() {
    const detail = opportunity({ description: 'Pesquisa com pessoas usuárias.' })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.includes('/duplicate-candidates')) return new Response(JSON.stringify({ items: [] }))
        if (url.includes('/matches?')) {
          return new Response(JSON.stringify({ items: [assessmentPayload] }))
        }
        if (url.includes('/applications?')) {
          return new Response(JSON.stringify({ items: [], total: 0, offset: 0, limit: 1 }))
        }
        if (url.endsWith('/opportunities/opportunity-1')) {
          return new Response(
            JSON.stringify({
              id: detail.id,
              fingerprint: detail.fingerprint,
              fingerprint_version: detail.fingerprintVersion,
              title: detail.title,
              company_id: detail.companyId,
              company_name: detail.companyName,
              location: detail.location,
              work_mode: detail.workMode,
              seniority: detail.seniority,
              contract_type: detail.contractType,
              description: detail.description,
              lifecycle_status: detail.lifecycleStatus,
              published_at: detail.publishedAt,
              recency_effective_date: detail.recencyEffectiveDate,
              recency_basis: detail.recencyBasis,
              created_at: detail.createdAt,
              version: detail.version,
              compensations: [],
              skills: [],
              occurrences: [],
              normalization_results: [],
              sibling_locations: [],
              relevance_mark: null,
            }),
          )
        }
        return new Response('{}', { status: 404 })
      }),
    )
    const container = renderWithProviders(
      <MemoryRouter initialEntries={['/opportunities/opportunity-1']}>
        <Routes>
          <Route path="/opportunities/:opportunityId" element={<OpportunityDetailPage />} />
        </Routes>
      </MemoryRouter>,
      false,
    )
    await flush(8)
    return container
  }

  function before(first: Element, second: Element) {
    return Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING)
  }

  it('mantém a ordem do DOM: voltar, bloco do título, painel de decisão, primeira seção', async () => {
    const container = await renderDetail()

    const content = container.querySelector('#conteudo') as HTMLElement
    const back = content.querySelector('a[href="/inbox"]') as HTMLElement
    const kicker = container.querySelector('header p') as HTMLElement
    const title = container.querySelector('h1') as HTMLElement
    const facts = container.querySelector('#resumo') as HTMLElement
    const panel = container.querySelector('aside[aria-labelledby="painel-decisao"]') as HTMLElement
    const firstSection = panel.nextElementSibling?.querySelector('section') as HTMLElement

    expect(back.textContent).toContain('Voltar')
    expect(kicker.textContent).toBe('Oportunidade')
    expect(title.textContent).toBe('Backend Engineer')
    expect(facts.textContent).toContain('Acme')
    expect(facts.textContent).toContain('Remoto')
    expect(firstSection.querySelector('h2')?.textContent).toBe('Descrição')
    expect(before(back, title)).toBe(true)
    expect(before(title, facts)).toBe(true)
    expect(before(facts, panel)).toBe(true)
    expect(before(panel, firstSection)).toBe(true)
    // The panel carries the human actions that already existed.
    expect(panel.textContent).toContain('Relevante')
    expect(panel.querySelector('#candidatura')).not.toBeNull()
    expect(panel.textContent).toContain('Registrar interesse')
  })

  it('separa o matching determinístico da análise de IA em regiões rotuladas', async () => {
    const container = await renderDetail()

    const deterministic = container.querySelector('#decisao') as HTMLElement
    const analysis = container.querySelector('#analise') as HTMLElement
    expect(deterministic.tagName).toBe('SECTION')
    expect(analysis.tagName).toBe('SECTION')
    expect(deterministic.contains(analysis)).toBe(false)
    expect(analysis.contains(deterministic)).toBe(false)

    const nameOf = (section: HTMLElement) =>
      container.querySelector(`#${section.getAttribute('aria-labelledby')}`)?.textContent
    expect(nameOf(deterministic)).toBe('Decisão')
    expect(nameOf(analysis)).toBe('Análise semântica')
    expect(deterministic.textContent).toContain('Recomendada')
    expect(deterministic.textContent).not.toContain('Analisar com IA')
    expect(analysis.textContent).toContain('Analisar com IA')
    expect(analysis.textContent).toContain('consultiv')
    expect(before(deterministic, analysis)).toBe(true)
  })
})
