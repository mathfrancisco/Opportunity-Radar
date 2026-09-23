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

    expect(primary?.className).toContain('bg-ink')
    expect(secondary?.className).toContain('border-line-strong')
    expect(secondary?.className).not.toContain('bg-ink')
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
