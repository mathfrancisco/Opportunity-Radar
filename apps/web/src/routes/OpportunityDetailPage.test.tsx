import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { type OpportunityDetail } from '../features/opportunities/api'
import { DuplicateCandidates } from './OpportunityDetailPage'

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
    createdAt: '2026-09-05T00:00:00Z',
    version: 1,
    compensations: [],
    skills: [],
    occurrences: [],
    normalizationResults: [],
    relevanceMark: null,
    ...overrides,
  }
}

function candidate(overrides: Record<string, unknown> = {}) {
  return {
    id: 'candidate-1',
    opportunity_id: 'opportunity-1',
    duplicate_opportunity_id: 'opportunity-2',
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
