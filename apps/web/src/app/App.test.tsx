import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type ReactElement, type ReactNode, act } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { setAuthSession, setAuthTokenGetter } from '../lib/api'
import { App } from './App'

const clerkMock = vi.hoisted(() => ({
  getToken: vi.fn(async () => 'vitest-token'),
  userId: 'user-a' as string | null,
  isLoaded: true,
  isSignedIn: true,
}))

vi.mock('@clerk/react', () => ({
  Show: ({ children }: { children?: ReactNode }) => children ?? null,
  UserButton: () => null,
  SignIn: (props: { fallbackRedirectUrl?: string; path?: string; routing?: string; signUpUrl?: string }) => (
    <div
      data-fallback-redirect-url={props.fallbackRedirectUrl}
      data-path={props.path}
      data-routing={props.routing}
      data-sign-up-url={props.signUpUrl}
    >
      Entrar na conta
    </div>
  ),
  SignUp: (props: { fallbackRedirectUrl?: string; path?: string; routing?: string; signInUrl?: string }) => (
    <div
      data-fallback-redirect-url={props.fallbackRedirectUrl}
      data-path={props.path}
      data-routing={props.routing}
      data-sign-in-url={props.signInUrl}
    >
      Criar conta
    </div>
  ),
  useAuth: () => clerkMock,
}))

afterEach(() => {
  setAuthTokenGetter(null)
  setAuthSession(null, false)
  clerkMock.isLoaded = true
  clerkMock.isSignedIn = true
  clerkMock.userId = 'user-a'
  clerkMock.getToken.mockClear()
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
  setAuthSession(clerkMock.userId, clerkMock.isSignedIn)
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
    setAuthTokenGetter(clerkMock.getToken)
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
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const container = renderApp(<App />, '/')

    expect(container.querySelector('h1')?.textContent).toBe('Encontre oportunidades alinhadas à sua carreira.')
    expect(container.textContent).toContain('Entrar')
    expect(container.textContent).toContain('Criar conta')
    expect(container.querySelector('a[href="/sign-in"]')?.textContent).toContain('Entrar')
    expect(container.querySelector('a[href="/sign-up"]')?.textContent).toContain('Criar conta')
    expect(container.querySelector('[data-testid="product-preview"]')?.textContent).toContain('Demonstração com dados fictícios')
    expect(container.querySelectorAll('details')).toHaveLength(3)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(clerkMock.getToken).not.toHaveBeenCalled()
  })

  it('não busca dados nem token enquanto Clerk ainda carrega', () => {
    clerkMock.isLoaded = false
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const container = renderApp(<App />, '/')

    expect(container.textContent).toContain('Verificando sessão')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(clerkMock.getToken).not.toHaveBeenCalled()
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
    expect(container.querySelector('a[href="/"]')?.textContent).toContain('Opportunity Radar')
  })

  it.each([
    ['/sign-in/verify', 'Entrar na conta', '/sign-in', '/sign-up'],
    ['/sign-up/verify', 'Criar conta', '/sign-up', '/sign-in'],
  ])('usa roteamento por caminho em %s', (path, expectedText, componentPath, adjacentAuthPath) => {
    clerkMock.isSignedIn = false
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } })
    const container = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    const form = container.querySelector('[data-routing="path"]')

    expect(form?.textContent).toContain(expectedText)
    expect(form?.getAttribute('data-path')).toBe(componentPath)
    expect(form?.getAttribute('data-fallback-redirect-url')).toBe('/')
    expect(form?.getAttribute('data-sign-up-url') ?? form?.getAttribute('data-sign-in-url')).toBe(adjacentAuthPath)
  })

  it('usa links locais da página pública para as rotas Clerk', () => {
    clerkMock.isSignedIn = false
    const container = renderApp(<App />, '/')

    expect(container.querySelectorAll('a[href="/sign-in"]')).not.toHaveLength(0)
    expect(container.querySelectorAll('a[href="/sign-up"]')).not.toHaveLength(0)
  })

  it('mantém a marca e os CTAs do cabeçalho utilizáveis em telas pequenas', () => {
    clerkMock.isSignedIn = false
    const container = renderApp(<App />, '/')
    const homeLink = container.querySelector('a[aria-label="Opportunity Radar — início"]')

    expect(homeLink?.className).toContain('min-h-11')
    expect(homeLink?.className).toContain('min-w-11')
    expect(homeLink?.querySelector(':scope > span > span:nth-child(2)')?.className).toContain('hidden')
  })

  it('oferece alvos de toque no rodapé público', () => {
    clerkMock.isSignedIn = false
    const container = renderApp(<App />, '/')

    for (const link of container.querySelectorAll('footer a')) {
      expect(link.className).toContain('min-h-11')
    }
  })

  it('oferece alvos de toque no shell de autenticação', () => {
    clerkMock.isSignedIn = false
    const container = renderApp(<App />, '/sign-in/sso-callback')

    for (const link of container.querySelectorAll('a[href="/"]')) {
      expect(link.className).toContain('min-h-11')
    }
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
    'mantém usuários sem capacidade resolvida em verificação na rota owner %s',
    (path) => {
    const client = new QueryClient({ defaultOptions: { queries: { enabled: false } } })
    const container = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(container.querySelector('[role="status"]')?.textContent).toBe('Verificando sessão…')
    expect(container.querySelector('nav a[href="/sources"]')).toBeNull()
    expect(container.querySelector('nav a[href="/companies"]')).toBeNull()
    expect(container.querySelector('nav a[href="/status"]')).toBeNull()
    },
  )
})
