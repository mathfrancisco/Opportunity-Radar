import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { StatusPage } from './StatusPage'

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

describe('StatusPage', () => {
  it('expõe a prontidão da API e do banco e a próxima ação quando estão disponíveis', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ status: 'ok', ai: { status: 'healthy' } }), { status: 200 }),
        ),
    )

    const container = renderPage(<StatusPage />)
    await flush()

    expect(container.textContent).toContain('Radar pronto para começar')
    expect(container.textContent).toContain('Próxima ação')
    expect(container.textContent).toContain('A prontidão confirma que a API e a conexão com o banco de dados estão disponíveis.')
    expect(container.textContent).not.toContain('IA está indisponível')
    expect(
      [...container.querySelectorAll('a')].find((link) => link.textContent === 'Ver fontes')?.getAttribute('href'),
    ).toBe('/sources')
  })

  it('apresenta estado degradado quando os sinais de saúde não estão completos', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }), { status: 200 }))
        .mockResolvedValueOnce(
          new Response(JSON.stringify({ status: 'ok', ai: { status: 'disabled' } }), { status: 200 }),
        ),
    )

    const container = renderPage(<StatusPage />)
    await flush()

    expect(container.textContent).toContain('Radar disponível com recursos limitados')
    expect(container.textContent).toContain('Confira a configuração e a saúde dos serviços')
    expect(container.textContent).toContain('IA está indisponível')
    expect([...container.querySelectorAll('a')].find((link) => link.textContent === 'Ver fontes')).toBeUndefined()
  })
})
