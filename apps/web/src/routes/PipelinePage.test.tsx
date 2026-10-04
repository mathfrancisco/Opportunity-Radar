import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { PipelinePage } from './PipelinePage'

afterEach(() => vi.unstubAllGlobals())

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderPage(element: ReactElement): HTMLElement {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function application(id: string, stage: string) {
  return {
    id,
    opportunity_id: `opportunity-${id}`,
    profile_version_id: 'profile-1',
    current_stage: stage,
    status: stage === 'REJECTED' ? 'CLOSED' : 'ACTIVE',
    outcome: null,
    next_action: null,
    next_action_at: null,
    notes: null,
    applied_at: null,
    started_at: '2026-01-01T10:00:00Z',
    closed_at: null,
    version: 1,
    allowed_transitions: [],
    history: [],
  }
}

describe('PipelinePage', () => {
  it('alterna entre candidaturas em andamento e encerradas, mantendo os cartões de cada visão', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = new URL(String(input), 'http://localhost')
        const closed = url.searchParams.get('application_status') === 'CLOSED'
        const items = closed ? [application('closed', 'REJECTED')] : [application('active', 'INTERVIEW')]
        return new Response(JSON.stringify({ items, total: items.length, offset: 0, limit: 100 }), {
          status: 200,
        })
      }),
    )

    const container = renderPage(<PipelinePage />)
    await flush()

    const active = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.startsWith('Em andamento'),
    )
    const closed = [...container.querySelectorAll('button')].find((button) =>
      button.textContent?.startsWith('Encerradas'),
    )
    expect(active?.getAttribute('aria-pressed')).toBe('true')
    expect(container.textContent).toContain('Entrevista')
    expect(
      [...container.querySelectorAll('a')].find((link) => link.textContent === 'Ver oportunidade')?.getAttribute('href'),
    ).toBe('/opportunities/opportunity-active')

    act(() => closed?.click())
    await flush()

    expect(closed?.getAttribute('aria-pressed')).toBe('true')
    expect(active?.getAttribute('aria-pressed')).toBe('false')
    expect(container.textContent).toContain('Recusada')
    expect(
      [...container.querySelectorAll('a')].find((link) => link.textContent === 'Ver oportunidade')?.getAttribute('href'),
    ).toBe('/opportunities/opportunity-closed')
  })

  it('pagina mais de 100 candidaturas usando offset e limit do backend', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = new URL(String(input), 'http://localhost')
        const closed = url.searchParams.get('application_status') === 'CLOSED'
        const offset = url.searchParams.get('offset')
        const items = closed
          ? []
          : offset === '12'
            ? [application('active-second-page', 'SCREENING')]
            : [application('active-first-page', 'INTERVIEW')]
        return new Response(JSON.stringify({ items, total: closed ? 0 : 124, offset: Number(offset), limit: 12 }), {
          status: 200,
        })
      }),
    )

    const container = renderPage(<PipelinePage />)
    await flush()

    expect(container.textContent).toContain('Entrevista')
    const pageTwo = [...container.querySelectorAll('button')].find(
      (button) => button.getAttribute('aria-label') === 'Página 2',
    )
    act(() => pageTwo?.click())
    await flush()

    expect(container.textContent).toContain('Triagem')
    expect(container.textContent).toContain('Exibindo 13 a 24 de 124 candidaturas')
    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls.map(([input]) => String(input))
    expect(
      calls.some(
        (url) =>
          url.includes('application_status=ACTIVE') && url.includes('offset=12') && url.includes('limit=12'),
      ),
    ).toBe(true)
  })
})
