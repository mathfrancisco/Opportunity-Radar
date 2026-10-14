import { ClerkProvider, useAuth } from '@clerk/react'
import { Fragment, type ReactNode, useLayoutEffect, useRef } from 'react'
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { App } from './App'
import { setAuthSession, setAuthTokenGetter } from '../lib/api'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

/**
 * Wires Clerk into the API layer and isolates the query cache per identity.
 *
 * The cache is dropped synchronously during render when the identity changes, and children are
 * remounted under an identity key, so no observer can keep showing the previous user's data.
 */
/**
 * Wires Clerk into the API layer and isolates the query cache per identity.
 *
 * The cache is dropped synchronously during render when the identity changes, and children are
 * remounted under an identity key, so no observer can keep showing the previous user's data.
 */
export function ClerkTokenBridge({ children }: { children: ReactNode }) {
  const { getToken, isSignedIn, userId } = useAuth()
  const queryClient = useQueryClient()
  const identity = isSignedIn === true && userId ? userId : null
  const previousIdentity = useRef(identity)

  if (previousIdentity.current !== identity) {
    previousIdentity.current = identity
    void queryClient.cancelQueries()
    queryClient.clear()
  }

  useLayoutEffect(() => {
    setAuthTokenGetter(getToken)
  }, [getToken])

  useLayoutEffect(() => {
    setAuthSession(identity, identity !== null)
  }, [identity])

  useLayoutEffect(
    () => () => {
      setAuthTokenGetter(null)
      setAuthSession(null, false)
      void queryClient.cancelQueries()
      queryClient.clear()
    },
    [queryClient],
  )

  return <Fragment key={identity ?? 'signed-out'}>{children}</Fragment>
}

export function WebApplication({ publishableKey }: { publishableKey: string }) {
  const key = publishableKey.trim()
  if (!key) {
    return (
      <main className="min-h-screen bg-canvas p-6 text-ink">
        <div className="mx-auto max-w-2xl rounded-panel border border-danger-line bg-danger-surface p-6 text-danger-ink" role="alert">
          <h1 className="text-section">Configuração de autenticação ausente</h1>
          <p className="mt-2 text-sm">
            Defina VITE_CLERK_PUBLISHABLE_KEY para habilitar o acesso. A autenticação não foi iniciada.
          </p>
        </div>
      </main>
    )
  }

  return (
    <ClerkProvider
      afterSignOutUrl="/"
      publishableKey={key}
      signInFallbackRedirectUrl="/"
      signInUrl="/sign-in"
      signUpFallbackRedirectUrl="/"
      signUpUrl="/sign-up"
    >
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ClerkTokenBridge>
            <App />
          </ClerkTokenBridge>
        </BrowserRouter>
      </QueryClientProvider>
    </ClerkProvider>
  )
}
