import { createElement, type ReactNode } from 'react'
import { vi } from 'vitest'

// Only the presentational Clerk controls are stubbed here, and the user is signed out by
// default so the shell's session query stays disabled (tests that need a session mock
// useAuth or useSession themselves). The token getter is deliberately NOT installed
// globally: tests that need one call installTestAuth(), so a missing bridge fails.
vi.mock('@clerk/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@clerk/react')>()),
  useAuth: () => ({ isLoaded: true, isSignedIn: false, userId: null }),
  Show: ({ children }: { children?: ReactNode }) => children ?? null,
  UserButton: () => createElement('button', { 'aria-label': 'Conta', type: 'button' }),
}))
