import { installTestAuth } from '../test/auth'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AIBudgetCard } from './AIBudgetCard'
import { render } from './testing'

installTestAuth()

afterEach(() => vi.unstubAllGlobals())

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderWithClient(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>)
}

function budget(overrides: Record<string, unknown> = {}) {
  return {
    state: 'enabled',
    day: '2026-10-17T00:00:00Z',
    resets_at: '2026-10-18T00:00:00Z',
    interactive_reserve_requests: 100,
    models: [
      {
        model: 'openai/gpt-oss-120b',
        provider: 'groq',
        provider_requests_limit: 1000,
        requests_soft_limit: 850,
        requests_used: 120,
        requests_remaining: 880,
        requests_remaining_operational: 730,
        tokens_limit: 170000,
        tokens_used: 40000,
        tokens_remaining: 130000,
      },
      {
        model: 'openai/gpt-oss-20b',
        provider: 'groq',
        provider_requests_limit: 1000,
        requests_soft_limit: 850,
        requests_used: 0,
        requests_remaining: 1000,
        requests_remaining_operational: 850,
        tokens_limit: 170000,
        tokens_used: 0,
        tokens_remaining: 170000,
      },
    ],
    ...overrides,
  }
}

function metrics(byTask: unknown[]) {
  return {
    generated_at: '2026-10-17T12:00:00Z',
    current_model: 'openai/gpt-oss-120b',
    pending: 0,
    windows: [],
    ai: {
      state: 'enabled',
      window_hours: 24,
      by_model: [],
      cache_hit_rate: null,
      by_task: byTask,
    },
  }
}

function stub(
  budgetBody: unknown,
  metricsBody: unknown = metrics([]),
  budgetStatus = 200,
) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      const url = String(input)
      if (url.endsWith('/ai-budget')) {
        return new Response(JSON.stringify(budgetBody), { status: budgetStatus })
      }
      if (url.endsWith('/analysis-metrics')) {
        return new Response(JSON.stringify(metricsBody), { status: 200 })
      }
      return new Response('{}', { status: 404 })
    }),
  )
}

describe('AIBudgetCard', () => {
  it('mostra o consumo contra o limite diário de 1 000 requisições por modelo', async () => {
    stub(budget())

    const container = renderWithClient(<AIBudgetCard />)
    await flush()

    const text = container.textContent ?? ''
    expect(text).toContain('openai/gpt-oss-120b')
    expect(text).toMatch(/120\s*\/\s*1\.000 req hoje/)
    expect(text).toContain('restam 880 req')
    expect(text).toMatch(/tokens 40\.000 \/ 170\.000 \(restam 130\.000\)/)
    expect(text).toContain('openai/gpt-oss-20b')
    expect(text).toContain('restam 1.000 req')
    expect(text).toContain('Reserva interativa: 100 req')
    expect(text).toContain('zera às 00:00 UTC')
    const bar = container.querySelector('[role="img"]')
    expect(bar?.getAttribute('aria-label')).toBe(
      'openai/gpt-oss-120b: 120 de 1000 requisições hoje',
    )
  })

  it('mostra o custo médio por vaga e a taxa de fallback por tarefa', async () => {
    stub(
      budget(),
      metrics([
        {
          task: 'job_match',
          jobs: 4,
          cache_hits: 2,
          requests: 5,
          tokens: 4400,
          avg_tokens_per_job: 1100,
          avg_requests_per_job: 1.25,
          fallback_jobs: 1,
          fallback_rate: 0.25,
        },
        {
          task: 'job_classification',
          jobs: 0,
          cache_hits: 0,
          requests: 0,
          tokens: 0,
          avg_tokens_per_job: null,
          avg_requests_per_job: null,
          fallback_jobs: 0,
          fallback_rate: null,
        },
      ]),
    )

    const container = renderWithClient(<AIBudgetCard />)
    await flush()

    const text = container.textContent ?? ''
    expect(text).toContain('Análise de encaixe')
    expect(text).toMatch(/1\.100\s+tokens\/vaga · fallback 25% · 4 vagas/)
    expect(text).toMatch(/Classificação[\s\S]*— tokens\/vaga · fallback —/)
  })

  it('não diz "desligada" enquanto o orçamento carrega', async () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))

    const container = renderWithClient(<AIBudgetCard />)
    await flush(1)

    expect(container.textContent).not.toContain('desligada')
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('explica a IA desligada e a bloqueada por configuração', async () => {
    stub(budget({ state: 'disabled', models: [] }))
    const off = renderWithClient(<AIBudgetCard />)
    await flush()
    expect(off.textContent).toContain('IA desligada')

    stub(budget({ state: 'blocked_by_configuration', models: [] }))
    const blocked = renderWithClient(<AIBudgetCard />)
    await flush()
    expect(blocked.textContent).toContain(
      'Bloqueada por configuração: nenhum provedor de IA tem chave.',
    )
    expect(blocked.textContent).not.toMatch(/Groq/)
  })

  it('mostra o provedor ao lado do modelo, sem o prefixo', async () => {
    stub(
      budget({
        models: [
          {
            model: 'cerebras:gpt-oss-120b',
            provider: 'cerebras',
            provider_requests_limit: null,
            requests_soft_limit: 100,
            requests_used: 3,
            requests_remaining: null,
            requests_remaining_operational: 97,
            tokens_limit: 1000,
            tokens_used: 10,
            tokens_remaining: 990,
          },
        ],
      }),
    )

    const container = renderWithClient(<AIBudgetCard />)
    await flush()

    const text = container.textContent ?? ''
    expect(text).toContain('cerebras')
    expect(text).toContain('gpt-oss-120b')
    expect(text).not.toContain('cerebras:gpt-oss-120b')
  })

  it('avisa quando o orçamento não pôde ser carregado', async () => {
    stub({}, metrics([]), 500)

    const container = renderWithClient(<AIBudgetCard />)
    await flush()

    expect(container.textContent).toContain('Não foi possível carregar o orçamento de IA.')
  })
})
