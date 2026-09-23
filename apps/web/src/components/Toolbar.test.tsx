import { describe, expect, it, vi } from 'vitest'
import { Toolbar } from './Toolbar'
import { render } from './testing'

const options = [
  { value: '', label: 'Todas' },
  { value: 'true', label: 'Já aplicada' },
] as const

describe('Toolbar', () => {
  it('diz qual filtro está ativo sem depender da cor', () => {
    const container = render(
      <Toolbar label="Candidatura" onChange={() => {}} options={options} value="true" />,
    )
    const pressed = [...container.querySelectorAll('button')].map((button) =>
      button.getAttribute('aria-pressed'),
    )

    expect(pressed).toEqual(['false', 'true'])
  })

  it('nomeia o grupo mesmo quando o rótulo não aparece', () => {
    const container = render(
      <Toolbar label="Janela das métricas" onChange={() => {}} options={options} value="" />,
    )
    const group = container.querySelector('[role="group"]')

    expect(group?.getAttribute('aria-label')).toBe('Janela das métricas')
    expect(group?.textContent).not.toContain('Janela das métricas')
  })

  it('mostra o rótulo sem repeti-lo para o leitor de tela', () => {
    const container = render(
      <Toolbar label="Candidatura" onChange={() => {}} options={options} showLabel value="" />,
    )
    const visible = container.querySelector('span')

    expect(visible?.textContent).toBe('Candidatura')
    expect(visible?.getAttribute('aria-hidden')).toBe('true')
  })

  it('devolve o valor da opção escolhida', () => {
    const change = vi.fn()
    const container = render(
      <Toolbar label="Candidatura" onChange={change} options={options} value="" />,
    )

    container.querySelectorAll('button')[1].click()
    expect(change).toHaveBeenCalledWith('true')
  })
})
