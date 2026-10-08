import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { render } from '../components/testing'
import { HomologationQueuePage } from './HomologationQueuePage'

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
    expect(
      container.querySelector('a[href="/sources/homologation-queue"]')?.getAttribute('aria-current'),
    ).toBe('page')
  })
})
