import { describe, expect, it } from 'vitest'
import { Field, controlClassName } from './Field'
import { render } from './testing'

describe('Field', () => {
  it('associa o rótulo ao controle sem depender de um id', () => {
    const container = render(
      <Field label="Score mínimo">
        <input className={controlClassName} />
      </Field>,
    )
    const label = container.querySelector('label')

    expect(label?.querySelector('input')).not.toBeNull()
    expect(label?.textContent).toContain('Score mínimo')
  })

  it('esconde o rótulo sem tirá-lo do leitor de tela', () => {
    const container = render(
      <Field hiddenLabel label="Buscar">
        <input />
      </Field>,
    )
    const caption = container.querySelector('span')

    expect(caption?.className).toBe('sr-only')
    expect(caption?.textContent).toBe('Buscar')
  })

  it('mostra a dica abaixo do controle quando existe', () => {
    const container = render(
      <Field hint="Entre 0 e 100" label="Score mínimo">
        <input />
      </Field>,
    )

    expect(container.textContent).toContain('Entre 0 e 100')
  })
})

describe('Field em erro', () => {
  it('liga o erro ao controle em vez de só pintá-lo de vermelho', () => {
    const container = render(
      <Field error="Informe um valor entre 0 e 100" label="Score mínimo">
        <input className={controlClassName} />
      </Field>,
    )
    const input = container.querySelector('input')
    const described = input?.getAttribute('aria-describedby')

    expect(input?.getAttribute('aria-invalid')).toBe('true')
    expect(described).toBeTruthy()
    expect(container.querySelector(`#${CSS.escape(described!)}`)?.textContent).toBe(
      'Informe um valor entre 0 e 100',
    )
  })

  it('não marca o controle como inválido sem erro', () => {
    const container = render(
      <Field label="Score mínimo">
        <input />
      </Field>,
    )

    expect(container.querySelector('input')?.getAttribute('aria-invalid')).toBeNull()
  })
})
