import { describe, expect, it } from 'vitest'
import { Chip } from './Chip'
import { render } from './testing'

describe('Chip', () => {
  it('é outlined, com raio de chip, por padrão', () => {
    const chip = render(<Chip>Startup</Chip>).firstElementChild

    expect(chip?.textContent).toBe('Startup')
    expect(chip?.className).toContain('rounded-chip')
    expect(chip?.className).toContain('border-line-strong')
  })

  it('troca o tom em vez de empilhar duas cores', () => {
    const chip = render(<Chip tone="border-danger-line text-danger-ink">Falhou</Chip>)
      .firstElementChild

    expect(chip?.className).toContain('border-danger-line')
    expect(chip?.className).not.toContain('border-line-strong')
  })

  it('mostra o ponto de cor só quando pedido, escondido do leitor de tela', () => {
    const plain = render(<Chip>A</Chip>)
    const dotted = render(<Chip dot>B</Chip>)

    expect(plain.querySelector('span span')).toBeNull()
    expect(dotted.querySelector('span span')?.getAttribute('aria-hidden')).toBe('true')
    expect(dotted.textContent).toBe('B')
  })
})
