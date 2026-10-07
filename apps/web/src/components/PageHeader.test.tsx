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

  it('desenha o eyebrow como kicker antes do h1 e, sem ele, não desenha nada', () => {
    const withKicker = render(<PageHeader eyebrow="Decidir" title="Inbox" />)
    const kicker = withKicker.querySelector('header p')
    expect(kicker?.textContent).toBe('Decidir')
    expect(kicker?.nextElementSibling?.tagName).toBe('H1')

    expect(render(<PageHeader title="Inbox" />).querySelector('header p')).toBeNull()
  })

  it('desenha o slot de metadados do título depois do h1', () => {
    const container = render(<PageHeader meta={<p data-testid="meta">Acme</p>} title="Vaga" />)
    const h1 = container.querySelector('h1') as HTMLElement
    const meta = container.querySelector('[data-testid="meta"]') as HTMLElement
    expect(h1.compareDocumentPosition(meta) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('não desenha o slot de ação nem o subtítulo quando ausentes', () => {
    const container = render(<PageHeader title="Status" />)

    expect(container.querySelector('p')).toBeNull()
    expect(container.querySelector('button')).toBeNull()
  })
})
