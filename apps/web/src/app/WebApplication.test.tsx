import { act, type ReactElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { privateFetch } from '../lib/api'
import { ClerkTokenBridge, WebApplication } from './WebApplication'

const clerkMock = vi.hoisted(() => ({
  getToken: vi.fn(async () => 'bridge-token'),
  userId: 'user-a' as string | null,
  isLoaded: true,
  isSignedIn: true,
}))

vi.mock('@clerk/react', () => ({
  ClerkProvider: ({
    afterSignOutUrl,
    children,
    signInFallbackRedirectUrl,
    signInUrl,
    signUpFallbackRedirectUrl,
    signUpUrl,
  }: {
    afterSignOutUrl?: string
    children: ReactNode
    signInFallbackRedirectUrl?: string
    signInUrl?: string
    signUpFallbackRedirectUrl?: string
    signUpUrl?: string
  }) => (
    <div
      data-after-sign-out-url={afterSignOutUrl}
      data-sign-in-fallback-redirect-url={signInFallbackRedirectUrl}
      data-sign-in-url={signInUrl}
      data-sign-up-fallback-redirect-url={signUpFallbackRedirectUrl}
      data-sign-up-url={signUpUrl}
      data-testid="clerk-provider"
    >
      {children}
    </div>
  ),
  Show: ({ children, when }: { children: ReactNode; when: string }) =>
    when === 'signed-in' && clerkMock.isSignedIn ? <>{children}</> : null,
  SignInButton: ({ children }: { children: ReactNode }) => <>{children}</>,
  SignUpButton: ({ children }: { children: ReactNode }) => <>{children}</>,
  UserButton: () => null,
  useAuth: () => clerkMock,
}))

const roots: Root[] = []

function render(element: ReactElement) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return container
}

function CacheProbe() {
  const { data } = useQuery({ queryKey: ['private-data'], queryFn: async () => null, enabled: false })
  return <output>{data}</output>
}

function bridgeElement(client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <ClerkTokenBridge>
        <CacheProbe />
      </ClerkTokenBridge>
    </QueryClientProvider>
  )
}

async function settleEffects() {
  await new Promise((resolve) => setTimeout(resolve, 0))
}

afterEach(() => {
  act(() => roots.splice(0).forEach((root) => root.unmount()))
  document.body.replaceChildren()
  clerkMock.getToken.mockClear()
  clerkMock.userId = 'user-a'
  clerkMock.isLoaded = true
  clerkMock.isSignedIn = true
  vi.unstubAllGlobals()
})

beforeEach(() => {
  clerkMock.userId = null
  clerkMock.isLoaded = true
  clerkMock.isSignedIn = false
})

describe('WebApplication', () => {
  it('shows a visible configuration failure when the Clerk key is missing', () => {
    const container = render(<WebApplication publishableKey="" />)

    expect(container.querySelector('[role="alert"]')?.textContent).toContain('VITE_CLERK_PUBLISHABLE_KEY')
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('Configuração')
    expect(container.querySelector('[data-testid="clerk-provider"]')).toBeNull()
  })

  it('mounts Clerk only when a publishable key exists', () => {
    const container = render(<WebApplication publishableKey="pk_test_example" />)

    expect(container.querySelector('[data-testid="clerk-provider"]')).not.toBeNull()
  })

  it('sets Clerk path routes and overview redirects on provider', () => {
    const container = render(<WebApplication publishableKey="pk_test_example" />)
    const provider = container.querySelector('[data-testid="clerk-provider"]')

    expect(provider?.getAttribute('data-sign-in-url')).toBe('/sign-in')
    expect(provider?.getAttribute('data-sign-up-url')).toBe('/sign-up')
    expect(provider?.getAttribute('data-sign-in-fallback-redirect-url')).toBe('/')
    expect(provider?.getAttribute('data-sign-up-fallback-redirect-url')).toBe('/')
    expect(provider?.getAttribute('data-after-sign-out-url')).toBe('/')
  })

  it.each([
    { userId: 'user-b', isSignedIn: true, label: 'troca de usuário' },
    { userId: null, isSignedIn: false, label: 'saída da conta' },
  ])('limpa cache privado em $label', async ({ userId, isSignedIn }) => {
    clerkMock.userId = 'user-a'
    clerkMock.isSignedIn = true
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(['private-data'], 'dados privados de A')
    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)
    roots.push(root)

    act(() => root.render(bridgeElement(client)))
    expect(container.textContent).toContain('dados privados de A')

    clerkMock.userId = userId
    clerkMock.isSignedIn = isSignedIn
    await act(async () => {
      root.render(bridgeElement(client))
      await settleEffects()
    })

    expect(client.getQueryData(['private-data'])).toBeUndefined()
    expect(container.textContent).not.toContain('dados privados de A')
  })

  it('uses Clerk token getter while mounted and rejects private requests after unmount', async () => {
    clerkMock.userId = 'user-a'
    clerkMock.isSignedIn = true
    const client = new QueryClient()
    const container = document.createElement('div')
    document.body.append(container)
    const root = createRoot(container)
    roots.push(root)
    const fetchMock = vi.fn<typeof fetch>(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    act(() => root.render(bridgeElement(client)))
    await privateFetch('/private/bridge')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer bridge-token')
    expect(clerkMock.getToken).toHaveBeenCalledTimes(1)

    act(() => root.unmount())
    roots.splice(roots.indexOf(root), 1)

    await expect(privateFetch('/private/unmounted')).rejects.toThrow('A autenticação não está disponível.')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
