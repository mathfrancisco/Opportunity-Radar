import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render } from '../components/testing'
import { LandingPage } from './LandingPage'

describe('LandingPage header', () => {
  it('keeps the header actions on one line at narrow widths', () => {
    const container = render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )
    const actions = container.querySelectorAll('header a[href="/sign-in"], header a[href="/sign-up"]')
    expect(Array.from(actions).map((a) => a.textContent)).toEqual(['Entrar', 'Criar conta'])
    for (const action of Array.from(actions)) expect(action.className).toContain('whitespace-nowrap')
  })
})
