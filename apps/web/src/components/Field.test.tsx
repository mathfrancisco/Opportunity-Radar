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
