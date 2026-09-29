import { describe, expect, it } from 'vitest'
import { PageHeader } from './PageHeader'
import { render } from './testing'

describe('PageHeader', () => {
  it('tem um único h1, o subtítulo e o slot de ação', () => {
    const container = render(
      <PageHeader
        actions={<button type="button">Adicionar fonte</button>}
        description="Fontes ativas"
        title="Fontes"
      />,
    )

    expect(container.querySelectorAll('h1')).toHaveLength(1)
    expect(container.querySelector('h1')?.textContent).toBe('Fontes')
    expect(container.textContent).toContain('Fontes ativas')
    expect(container.querySelector('button')?.textContent).toBe('Adicionar fonte')
  })

  it('não desenha o slot de ação nem o subtítulo quando ausentes', () => {
    const container = render(<PageHeader title="Status" />)

    expect(container.querySelector('p')).toBeNull()
    expect(container.querySelector('button')).toBeNull()
  })
})
