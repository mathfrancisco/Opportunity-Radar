import { describe, expect, it } from 'vitest'
import { Unavailable } from './Unavailable'
import { render } from './testing'

describe('Unavailable', () => {
  it('mostra o traço para o olho e o motivo para o leitor de tela', () => {
    const container = render(<Unavailable reason="sem execução na janela" />)

    expect(container.textContent).toContain('—')
    expect(container.querySelector('.sr-only')?.textContent).toBe('sem execução na janela')
    expect(container.querySelector('[aria-hidden="true"]')?.textContent).toBe('—')
  })

  it('nunca se confunde com zero', () => {
    const container = render(<Unavailable />)

    expect(container.textContent).not.toContain('0')
    expect(container.querySelector('span')?.getAttribute('title')).toBe('sem dados')
  })
})
