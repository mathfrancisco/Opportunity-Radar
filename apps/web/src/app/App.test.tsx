import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { App } from './App'

afterEach(() => vi.unstubAllGlobals())

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderApp(element: ReactElement): HTMLElement {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/rota-desconhecida']}>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('App', () => {
  it('apresenta Visão geral para URL desconhecida e marca esse item como atual', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: unknown) => {
        const url = String(input)
        if (url.endsWith('/saved-searches')) return new Response('[]', { status: 200 })
        if (url.endsWith('/overview')) return new Response(JSON.stringify({}), { status: 200 })
        if (url.endsWith('/analysis-metrics')) {
          return new Response(JSON.stringify({ enabled: false }), { status: 200 })
        }
        if (url.endsWith('/source-metrics')) {
          return new Response(JSON.stringify({ generated_at: '', windows: [] }), { status: 200 })
        }
        return new Response('{}', { status: 404 })
      }),
    )

    const container = renderApp(<App />)
    await flush(6)

    expect(container.querySelector('h1')?.textContent).toBe('O que move sua busca esta semana?')
    expect(container.querySelector('nav a[href="/"]')?.getAttribute('aria-current')).toBe('page')
    expect(container.querySelectorAll('nav [aria-current="page"]')).toHaveLength(1)
  })
})
