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
    opportunity_title: `Vaga ${id}`,
    company_name: `Empresa ${id}`,
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

function stubApplications(
  active: ReturnType<typeof application>[],
  closed: ReturnType<typeof application>[] = [],
) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      const url = new URL(String(input), 'http://localhost')
      const items = url.searchParams.get('application_status') === 'CLOSED' ? closed : active
      return new Response(JSON.stringify({ items, total: items.length, offset: 0, limit: 12 }), {
        status: 200,
      })
    }),
  )
}

describe('PipelinePage — quadro por etapa', () => {
  it('mostra toda etapa com nome e contagem, marca as vazias pelos dados e expõe cada uma como grupo rotulado', async () => {
    stubApplications([
      application('a', 'INTERESTED'),
      application('b', 'INTERVIEW'),
      application('c', 'INTERVIEW'),
    ])

    const container = renderPage(<PipelinePage />)
    await flush()

    expect(container.querySelector('h1')?.textContent).toBe(
      'Onde cada candidatura precisa de atenção?',
    )
    const board = container.querySelector('[role="group"][aria-label="Candidaturas por etapa"]')!
    const stages = [...board.querySelectorAll('section')].map((section) => ({
      name: section.querySelector('h3')?.firstElementChild?.textContent,
      count: section.querySelector('h3')?.lastElementChild?.textContent,
      empty: section.getAttribute('data-empty') === 'true',
      labelled: section.getAttribute('aria-labelledby') === section.querySelector('h3')?.id,
      cards: section.querySelectorAll('li').length,
    }))
    expect(stages.map(({ name, count, empty }) => [name, count, empty])).toEqual([
      ['Interesse', '1', false],
      ['Candidatura enviada', '0', true],
      ['Triagem', '0', true],
      ['Entrevista', '2', false],
      ['Teste técnico', '0', true],
      ['Etapa final', '0', true],
      ['Oferta', '0', true],
    ])
    expect(stages.every((stage) => stage.labelled)).toBe(true)
    expect(stages.map((stage) => stage.cards)).toEqual([1, 0, 0, 2, 0, 0, 0])
    // Abaixo de lg as vazias somem do layout: a frase as resume para tecnologia assistiva.
    expect(container.textContent).toContain(
      'Sem candidaturas em: Candidatura enviada, Triagem, Teste técnico, Etapa final, Oferta.',
    )
  })

  it('o seletor de visão troca o que é mostrado e expõe o estado em aria-pressed', async () => {
    stubApplications([application('a', 'INTERVIEW')], [application('z', 'REJECTED')])

    const container = renderPage(<PipelinePage />)
    await flush()

    const group = container.querySelector('[role="group"][aria-label="Visão das candidaturas"]')!
    const [active, closed] = [...group.querySelectorAll('button')]
    expect(active.getAttribute('aria-pressed')).toBe('true')
    expect(closed.getAttribute('aria-pressed')).toBe('false')
    expect(container.textContent).toContain('Vaga a')
    expect(container.textContent).not.toContain('Vaga z')

    act(() => closed.click())
    await flush()

    expect(active.getAttribute('aria-pressed')).toBe('false')
    expect(closed.getAttribute('aria-pressed')).toBe('true')
    expect(container.textContent).toContain('Vaga z')
    expect(container.textContent).not.toContain('Vaga a')
  })

  it('mostra o estado vazio quando não há candidatura alguma', async () => {
    stubApplications([])

    const container = renderPage(<PipelinePage />)
    await flush()

    expect(container.textContent).toContain('Nenhuma candidatura em andamento.')
    expect(
      container.querySelector('[role="group"][aria-label="Candidaturas por etapa"]'),
    ).toBeNull()
  })

  it('oferece nova tentativa quando o carregamento falha', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })))

    const container = renderPage(<PipelinePage />)
    await flush()

    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      'Não foi possível carregar',
    )
    expect(container.textContent).toContain('Tentar novamente')
  })
})

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
      [...container.querySelectorAll('a')].find((link) => link.textContent === 'Vaga active')?.getAttribute('href'),
    ).toBe('/opportunities/opportunity-active')
    expect(container.textContent).toContain('Empresa active')

    act(() => closed?.click())
    await flush()

    expect(closed?.getAttribute('aria-pressed')).toBe('true')
    expect(active?.getAttribute('aria-pressed')).toBe('false')
    expect(container.textContent).toContain('Recusada')
    expect(
      [...container.querySelectorAll('a')].find((link) => link.textContent === 'Vaga closed')?.getAttribute('href'),
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
