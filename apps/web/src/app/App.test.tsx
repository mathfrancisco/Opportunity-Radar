import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, act } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { setAuthTokenGetter } from '../lib/api'
import { App } from './App'

const clerkMock = vi.hoisted(() => ({
  getToken: vi.fn(async () => 'vitest-token'),
  isLoaded: true,
  isSignedIn: true,
}))

vi.mock('@clerk/react', () => ({
  SignIn: () => <div>Entrar na conta</div>,
  SignInButton: ({ children }: { children: ReactElement }) => children,
  SignUp: () => <div>Criar conta</div>,
  SignUpButton: ({ children }: { children: ReactElement }) => children,
  useAuth: () => clerkMock,
}))

afterEach(() => {
  clerkMock.isLoaded = true
  clerkMock.isSignedIn = true
  vi.unstubAllGlobals()
})

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function renderApp(element: ReactElement, initialEntry = '/rota-desconhecida'): HTMLElement {
  setAuthTokenGetter(clerkMock.getToken)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>{element}</MemoryRouter>
    </QueryClientProvider>,
  )
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="route-path">{location.pathname}</output>
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

  it('mostra página pública em / para visitantes sem sessão', () => {
    clerkMock.isSignedIn = false

    const container = renderApp(<App />, '/')

    expect(container.querySelector('h1')?.textContent).toBe('Encontre oportunidades alinhadas à sua carreira.')
    expect(container.textContent).toContain('Entrar')
    expect(container.textContent).toContain('Criar conta')
  })

  it.each(['/sign-in/verify', '/sign-up/verify'])('redireciona sessão ativa de %s para Visão geral', (path) => {
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } })
    const container = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <App />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(container.querySelector('h1')?.textContent).toBe('O que move sua busca esta semana?')
    expect(container.querySelector('[data-testid="route-path"]')?.textContent).toBe('/')
  })

  it.each([
    ['/sign-in/sso-callback', 'Entrar na conta'],
    ['/sign-up/sso-callback', 'Criar conta'],
  ])('renderiza formulário de %s para visitantes', (path, expectedText) => {
    clerkMock.isSignedIn = false
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } })
    const container = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(container.textContent).toContain(expectedText)
  })

  it('mantém visitantes fora das rotas de owner', () => {
    clerkMock.isSignedIn = false
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } })
    const container = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/sources']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(container.querySelector('h1')?.textContent).toBe('Encontre oportunidades alinhadas à sua carreira.')
    expect(container.querySelector('nav a[href="/sources"]')).toBeNull()
  })

  it.each(['/sources', '/sources/homologation-queue', '/companies', '/companies/owner', '/status'])(
    'mantém usuários sem capacidade verificada fora da rota owner %s',
    (path) => {
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } })
    const container = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(container.querySelector('h1')?.textContent).toBe('O que move sua busca esta semana?')
    expect(container.querySelector('nav a[href="/sources"]')).toBeNull()
    expect(container.querySelector('nav a[href="/companies"]')).toBeNull()
    expect(container.querySelector('nav a[href="/status"]')).toBeNull()
    },
  )
})
