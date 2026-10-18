import type { ReactNode } from 'react'

/** Test-only Clerk surface. This does not load or change production authentication. */
export function useAuth() {
  return { isLoaded: true, isSignedIn: true, userId: 'offline-ux-fixture', getToken: async () => 'offline-fixture' }
}

export function Show({ children }: { when?: string; children?: ReactNode }) {
  return children
}

export function UserButton() {
  return null
}
