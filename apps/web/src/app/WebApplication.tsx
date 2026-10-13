import { ClerkProvider, useAuth } from '@clerk/react'
import { type ReactNode, useLayoutEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { App } from './App'
import { AuthenticationControls } from './AuthenticationControls'
import { setAuthTokenGetter } from '../lib/api'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

function ClerkTokenBridge({ children }: { children: ReactNode }) {
  const { getToken } = useAuth()

  useLayoutEffect(() => {
    setAuthTokenGetter(getToken)
    return () => setAuthTokenGetter(null)
  }, [getToken])

  return children
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
    <ClerkProvider afterSignOutUrl="/" publishableKey={key}>
      <ClerkTokenBridge>
        <AuthenticationControls />
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </ClerkTokenBridge>
    </ClerkProvider>
  )
}
