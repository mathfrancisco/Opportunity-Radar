import { ClerkProvider, Show, SignInButton, SignUpButton, UserButton } from '@clerk/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { App } from './app/App'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

export function AuthenticationControls() {
  return (
    <div aria-label="Autenticação" className="fixed right-4 top-4 z-20 flex items-center gap-2">
      <Show when="signed-out">
        <SignInButton>
          <button className="h-9 rounded-control border border-line-strong bg-surface px-4 text-sm font-medium text-ink" type="button">
            Entrar
          </button>
        </SignInButton>
        <SignUpButton>
          <button className="h-9 rounded-control bg-accent px-4 text-sm font-semibold text-surface" type="button">
            Criar conta
          </button>
        </SignUpButton>
      </Show>
      <Show when="signed-in">
        <UserButton />
      </Show>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ClerkProvider afterSignOutUrl="/">
      <AuthenticationControls />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ClerkProvider>
  </StrictMode>,
)
