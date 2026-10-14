import { useAuth } from '@clerk/react'
import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

export function AuthPending() {
  return <p role="status">Verificando sessão…</p>
}

export function RequireSignedIn({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) return <AuthPending />
  if (!isSignedIn) return <Navigate replace to="/" />
  return children
}

// This web package has no API contract that confirms owner access. A successful general
// request or Clerk metadata cannot prove ownership, so owner UI stays disabled until an
// authenticated owner-only endpoint can supply that proof.
const ownerUiAvailable = false

export function RequireOwnerUi({ children }: { children: ReactNode }) {
  return (
    <RequireSignedIn>
      {ownerUiAvailable ? children : <Navigate replace to="/" />}
    </RequireSignedIn>
  )
}
