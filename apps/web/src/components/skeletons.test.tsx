import { describe, expect, it } from 'vitest'
import { CardListSkeleton, PanelSkeleton, Skeleton, TableSkeleton } from './skeletons'
import { render } from './testing'

describe('esqueletos de carregamento', () => {
  it('anuncia a região uma vez, com o mesmo texto que a faixa dizia', () => {
    const container = render(<CardListSkeleton count={6} label="Carregando fontes…" />)

    const regions = container.querySelectorAll('[role="status"]')
    expect(regions).toHaveLength(1)
    expect(regions[0].getAttribute('aria-busy')).toBe('true')
    expect(regions[0].textContent).toBe('Carregando fontes…')
  })

  it('tira a forma da árvore de acessibilidade', () => {
    const container = render(<TableSkeleton columns={5} label="Carregando empresas…" />)
    const shape = container.querySelector('[aria-hidden="true"]')

    expect(shape).not.toBeNull()
    expect(shape?.textContent).toBe('')
  })

  it('pulsa só quando o sistema não pede movimento reduzido', () => {
    const container = render(<PanelSkeleton label="Carregando a cobertura…" />)
    const shape = container.querySelector('[aria-hidden="true"]')

    expect(shape?.className).toContain('motion-safe:animate-pulse')
    expect(shape?.className.split(' ')).not.toContain('animate-pulse')
  })

  it('desenha o número de cartões e de linhas pedido', () => {
    const cards = render(<CardListSkeleton count={3} label="Carregando…" />)
    const table = render(<TableSkeleton columns={4} label="Carregando…" rows={2} />)

    expect(cards.querySelectorAll('.rounded-2xl')).toHaveLength(3)
    // Um cabeçalho e duas linhas, cada uma com quatro colunas.
    expect(table.querySelectorAll('.flex.gap-6')).toHaveLength(3)
    expect(table.querySelectorAll('.flex.gap-6 > span')).toHaveLength(12)
  })

  it('aceita forma própria sem perder o anúncio único', () => {
    const container = render(
      <Skeleton label="Carregando candidaturas…">
        <div>forma</div>
      </Skeleton>,
    )

    expect(container.querySelectorAll('[role="status"]')).toHaveLength(1)
    expect(container.querySelector('[aria-hidden="true"]')?.textContent).toBe('forma')
  })
})
