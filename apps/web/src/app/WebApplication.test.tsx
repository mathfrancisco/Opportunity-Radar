import { type ReactNode } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { WebApplication } from './WebApplication'

vi.mock('@clerk/react', () => ({
  ClerkProvider: ({ children }: { children: ReactNode }) => <div data-testid="clerk-provider">{children}</div>,
  Show: ({ children }: { children: ReactNode }) => <>{children}</>,
  SignInButton: ({ children }: { children: ReactNode }) => <>{children}</>,
  SignUpButton: ({ children }: { children: ReactNode }) => <>{children}</>,
  UserButton: () => null,
  useAuth: () => ({ getToken: async () => 'vitest-token', isLoaded: true, isSignedIn: false }),
}))

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
})
