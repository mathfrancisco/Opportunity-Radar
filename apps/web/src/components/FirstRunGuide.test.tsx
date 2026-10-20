import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { FirstRunGuide } from './FirstRunGuide'
import { render } from './testing'

describe('FirstRunGuide', () => {
  it('chama a montagem da bateia e leva ao perfil nos três passos', () => {
    const container = render(
      <MemoryRouter>
        <FirstRunGuide />
      </MemoryRouter>,
    )

    const title = container.querySelector('h2')
    expect(title?.textContent).toBe('Monte sua bateia')
    expect(title?.className).toContain('font-display')
    expect(Array.from(container.querySelectorAll('li p:first-of-type')).map((p) => p.textContent)).toEqual([
      'Diga o que você procura',
      'Diga o que você sabe',
      'Defina seus limites',
    ])
    expect(container.querySelector('a[href="/profile"]')?.textContent).toBe('Começar pelo perfil')
  })
})
