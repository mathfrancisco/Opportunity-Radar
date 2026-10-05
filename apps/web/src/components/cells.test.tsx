import { describe, expect, it } from 'vitest'
import { Avatar, DateTimeCell, PrimaryText, SecondaryText } from './cells'
import { render } from './testing'

describe('células de tabela', () => {
  it('põe o texto primário em destaque e o secundário em cinza', () => {
    const container = render(
      <>
        <PrimaryText>Engenheira de dados</PrimaryText>
        <SecondaryText>Acme · Remoto</SecondaryText>
      </>,
    )
    const [primary, secondary] = [...container.querySelectorAll('span')]

    expect(primary.className).toContain('font-semibold')
    expect(primary.className).toContain('text-ink')
    expect(secondary.className).toContain('text-muted')
    expect(secondary.textContent).toBe('Acme · Remoto')
  })

  it('separa data escura e hora cinza, com o instante máquina em <time>', () => {
    const container = render(<DateTimeCell timeZone="UTC" value="2026-09-29T14:05:00Z" />)
    const time = container.querySelector('time')
    const [day, hour] = [...container.querySelectorAll('span')]

    expect(time?.getAttribute('datetime')).toBe('2026-09-29T14:05:00.000Z')
    expect(day.textContent).toBe('29/09/2026')
    expect(day.className).toContain('text-ink')
    expect(hour.textContent).toBe('14:05')
    expect(hour.className).toContain('text-muted')
  })

  it('mostra o substituto quando a data é inválida', () => {
    const container = render(<DateTimeCell value="não é data" />)

    expect(container.querySelector('time')).toBeNull()
    expect(container.textContent).toBe('—')
  })

  it('tira as iniciais da primeira e da última palavra', () => {
    const text = (name: string) => render(<Avatar name={name} />).textContent

    expect(text('Ana Maria Souza')).toBe('AS')
    expect(text('  ana ')).toBe('A')
    expect(text('')).toBe('?')
  })

  it('desenha o avatar redondo e fora da árvore de acessibilidade', () => {
    const container = render(<Avatar name="Ana Souza" />)
    const avatar = container.firstElementChild

    expect(avatar?.textContent).toBe('AS')
    expect(avatar?.getAttribute('aria-hidden')).toBe('true')
    expect(avatar?.className).toContain('rounded-full')
  })
})
