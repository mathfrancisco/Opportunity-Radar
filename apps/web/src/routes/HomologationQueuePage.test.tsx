import { installTestAuth } from '../test/auth'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { render, visibleTextOutsideDetails } from '../components/testing'
import { HomologationQueuePage } from './HomologationQueuePage'

vi.mock('../lib/session', () => ({
  useSession: () => ({ data: { is_owner: true }, isError: false, isPending: false }),
}))

vi.mock('../components/HomologationQueue', () => ({
  HomologationQueue: () => <div>Fila carregada</div>,
}))

vi.mock('../features/profile/useProfile', () => ({
  useActiveProfile: () => ({ isPending: true, data: undefined }),
}))

describe('HomologationQueuePage', () => {
  it('marca Homologação como página atual e mostra o kicker de aquisição', () => {
    const container = render(
      <MemoryRouter>
        <HomologationQueuePage />
      </MemoryRouter>,
    )

    expect(container.querySelector('header')?.textContent).toContain('Aquisição')
    expect(container.querySelector('h1')?.textContent).toBe('Fila de homologação')
    expect(container.querySelector('header')?.textContent).toContain('habilite uma a uma')
    expect(visibleTextOutsideDetails(container)).not.toMatch(/[A-Z]{3,}_[A-Z_]+|\b[a-z]+(?:_[a-z]+)+\b/)
    expect(
      container.querySelector('a[href="/sources/homologation-queue"]')?.getAttribute('aria-current'),
    ).toBe('page')
  })
})

installTestAuth()
