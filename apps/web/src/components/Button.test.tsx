import { describe, expect, it } from 'vitest'
import { Button } from './Button'
import { render } from './testing'

describe('Button', () => {
  it('não submete o formulário em volta sem ser pedido', () => {
    const container = render(<Button>Executar agora</Button>)

    expect(container.querySelector('button')?.type).toBe('button')
  })

  it('submete quando o tipo é declarado', () => {
    const container = render(<Button type="submit">Salvar</Button>)

    expect(container.querySelector('button')?.type).toBe('submit')
  })

  it('separa a ação primária da secundária', () => {
    const primary = render(<Button>Primária</Button>).querySelector('button')
    const secondary = render(<Button variant="secondary">Secundária</Button>).querySelector(
      'button',
    )

    expect(primary?.className).toContain('bg-accent')
    expect(primary?.className).toContain('hover:bg-accent-hover')
    expect(secondary?.className).toContain('border-line-strong')
    expect(secondary?.className).not.toContain('bg-ink')
  })

  it('usa o raio de controle e oferece o tamanho sm de 32px', () => {
    const sm = render(
      <Button size="sm" variant="secondary">
        Pequeno
      </Button>,
    ).querySelector('button')

    expect(sm?.className).toContain('rounded-control')
    expect(sm?.className).toContain('h-8')
  })

  it('mostra o estado desabilitado em vez de apenas ignorar o clique', () => {
    const container = render(<Button disabled>Executar agora</Button>)
    const button = container.querySelector('button')

    expect(button?.disabled).toBe(true)
    expect(button?.className).toContain('disabled:opacity-40')
  })

  it('preserva a classe que a tela acrescenta', () => {
    const container = render(<Button className="self-end">Salvar</Button>)

    expect(container.querySelector('button')?.className).toContain('self-end')
  })
})
