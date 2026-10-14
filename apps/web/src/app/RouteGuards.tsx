import { useAuth } from '@clerk/react'
import { type ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useSession } from '../lib/session'

export function AuthPending() {
  return <p role="status">Verificando sessão…</p>
}

export function RequireSignedIn({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth()

  if (!isLoaded) return <AuthPending />
  if (!isSignedIn) return <Navigate replace to="/" />
  return children
}

export function RequireOwnerUi({ children }: { children: ReactNode }) {
  const { data, isError, isPending } = useSession()

  return (
    <RequireSignedIn>
      {data?.is_owner === true && !isPending && !isError ? children : <Navigate replace to="/" />}
    </RequireSignedIn>
  )
}
