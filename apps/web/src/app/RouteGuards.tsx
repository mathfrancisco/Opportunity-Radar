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
  const { data, isError, isFetching, isPending } = useSession()
  const isCapabilityPending = isPending || (isFetching && data === undefined)

  return (
    <RequireSignedIn>
      {isCapabilityPending ? <AuthPending /> : data?.is_owner === true && !isError ? children : <Navigate replace to="/" />}
    </RequireSignedIn>
  )
}
