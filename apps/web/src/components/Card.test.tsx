import { describe, expect, it } from 'vitest'
import { Card } from './Card'
import { render } from './testing'

describe('Card', () => {
  it('é uma div por padrão', () => {
    const container = render(<Card>conteúdo</Card>)

    expect(container.firstElementChild?.tagName).toBe('DIV')
    expect(container.firstElementChild?.className).toContain('border-line')
  })

  it('assume o elemento que a lista em volta exige', () => {
    const container = render(
      <ul>
        <Card as="li">item</Card>
      </ul>,
    )

    expect(container.querySelector('li')).not.toBeNull()
  })

  it('só oferece afordância de clique quando é clicável', () => {
    const plain = render(<Card>parado</Card>).firstElementChild
    const interactive = render(<Card interactive>clicável</Card>).firstElementChild

    expect(plain?.className).not.toContain('hover:border-ink')
    expect(interactive?.className).toContain('hover:border-ink')
  })
})
