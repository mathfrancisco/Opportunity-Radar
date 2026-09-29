import { act } from 'react'
import { describe, expect, it } from 'vitest'
import { PageSizeSelect } from './PageSizeSelect'
import { Pagination } from './Pagination'
import { render } from './testing'

function pagination(page: number, total: number, onPageChange: (page: number) => void = () => {}) {
  return render(
    <Pagination
      itemLabel="oportunidades"
      onPageChange={onPageChange}
      page={page}
      pageSize={15}
      total={total}
    />,
  )
}

const shown = (container: HTMLElement) =>
  [...container.querySelectorAll('li')].map((item) => item.textContent)

describe('janela de páginas', () => {
  const window = (page: number, total: number) =>
    shown(pagination(page, total * 15)).slice(1, -1)

  it('mostra todas as páginas quando são poucas', () => {
    expect(window(1, 1)).toEqual(['1'])
    expect(window(3, 7)).toEqual(['1', '2', '3', '4', '5', '6', '7'])
  })

  it('abre elipse dos dois lados no meio', () => {
    expect(window(5, 12)).toEqual(['1', '…', '4', '5', '6', '…', '12'])
  })

  it('só abre elipse de um lado perto das pontas', () => {
    expect(window(1, 12)).toEqual(['1', '2', '3', '4', '5', '…', '12'])
    expect(window(4, 12)).toEqual(['1', '2', '3', '4', '5', '…', '12'])
    expect(window(12, 12)).toEqual(['1', '…', '8', '9', '10', '11', '12'])
    expect(window(9, 12)).toEqual(['1', '…', '8', '9', '10', '11', '12'])
  })

  it('não usa elipse para esconder uma página só', () => {
    expect(window(5, 8)).toEqual(['1', '…', '4', '5', '6', '7', '8'])
  })
})

describe('Pagination', () => {
  it('diz o intervalo e o total em uma região viva educada', () => {
    const container = pagination(1, 145)
    const status = container.querySelector('p')

    expect(status?.textContent).toBe('Exibindo 1 a 15 de 145 oportunidades')
    expect(status?.getAttribute('aria-live')).toBe('polite')
  })

  it('corta o intervalo na última página', () => {
    const container = pagination(10, 145)

    expect(container.querySelector('p')?.textContent).toBe('Exibindo 136 a 145 de 145 oportunidades')
  })

  it('marca a página atual com aria-current, borda de acento e peso', () => {
    const container = pagination(5, 180)
    const current = container.querySelector('[aria-current="page"]')

    expect(current?.textContent).toBe('5')
    expect(current?.className).toContain('border-accent')
    expect(current?.className).toContain('text-accent-ink')
    expect(current?.className).toContain('font-semibold')
    expect(container.querySelectorAll('[aria-current]')).toHaveLength(1)
  })

  it('desenha números com elipse fora da árvore de acessibilidade', () => {
    const container = pagination(5, 180)

    expect(shown(container)).toEqual(['‹', '1', '…', '4', '5', '6', '…', '12', '›'])
    expect(container.querySelectorAll('span[aria-hidden="true"]').length).toBeGreaterThan(0)
  })

  it('nomeia anterior e próxima, e desabilita nos limites', () => {
    const first = pagination(1, 145)
    const last = pagination(10, 145)
    const prev = (c: HTMLElement) => c.querySelector<HTMLButtonElement>('[aria-label="Página anterior"]')
    const next = (c: HTMLElement) => c.querySelector<HTMLButtonElement>('[aria-label="Próxima página"]')

    expect(prev(first)?.disabled).toBe(true)
    expect(next(first)?.disabled).toBe(false)
    expect(prev(last)?.disabled).toBe(false)
    expect(next(last)?.disabled).toBe(true)
  })

  it('com uma página só, desabilita anterior e próxima e mostra a página 1', () => {
    const container = pagination(1, 10)

    expect(container.querySelector('p')?.textContent).toBe('Exibindo 1 a 10 de 10 oportunidades')
    expect(container.querySelectorAll('button:disabled')).toHaveLength(2)
    expect(container.querySelector('[aria-current="page"]')?.textContent).toBe('1')
  })

  it('com 0 itens, só diz que não há resultado', () => {
    const container = pagination(1, 0)

    expect(container.querySelector('p')?.textContent).toBe('Nenhum resultado')
    expect(container.querySelector('button')).toBeNull()
  })

  it('pede a página clicada, a anterior e a próxima', () => {
    const asked: number[] = []
    const container = pagination(5, 180, (page) => asked.push(page))
    const click = (selector: string) => act(() => container.querySelector<HTMLButtonElement>(selector)?.click())

    click('[aria-label="Página anterior"]')
    click('[aria-label="Próxima página"]')
    click('[aria-label="Página 12"]')

    expect(asked).toEqual([4, 6, 12])
  })

  it('corrige uma página fora do intervalo', () => {
    const container = pagination(99, 145)

    expect(container.querySelector('[aria-current="page"]')?.textContent).toBe('10')
  })

  it('é uma navegação com nome', () => {
    expect(pagination(1, 145).querySelector('nav')?.getAttribute('aria-label')).toBe('Paginação')
  })
})

describe('PageSizeSelect', () => {
  it('rotula "Itens por página" e avisa o número escolhido', () => {
    const chosen: number[] = []
    const container = render(<PageSizeSelect id="size" onChange={(v) => chosen.push(v)} value={25} />)
    const select = container.querySelector<HTMLSelectElement>('select')

    expect(select?.labels?.[0].textContent).toBe('Itens por página')
    expect(select?.value).toBe('25')
    act(() => {
      if (select) select.value = '50'
      select?.dispatchEvent(new Event('change', { bubbles: true }))
    })
    expect(chosen).toEqual([50])
  })

  it('aceita opções próprias', () => {
    const container = render(<PageSizeSelect id="size" onChange={() => {}} options={[5, 15]} value={5} />)

    expect([...container.querySelectorAll('option')].map((o) => o.value)).toEqual(['5', '15'])
  })
})
