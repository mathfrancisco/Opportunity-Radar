import { describe, expect, it } from 'vitest'
import { configText } from './configText'
import { ConfigValue } from './ConfigValue'
import { render } from './testing'

describe('configText', () => {
  it.each([
    ['acme', 'acme'],
    [3, '3'],
    [true, 'sim'],
    [false, 'não'],
    [null, '—'],
    [undefined, '—'],
    ['', '—'],
    [[], '—'],
    [['a', 'b'], 'a, b'],
    [{ a: 1, b: { c: 'x' } }, 'a: 1; b: c: x'],
  ])('%j vira texto legível', (value, expected) => {
    expect(configText(value)).toBe(expected)
  })

  it('nunca produz [object Object]', () => {
    expect(configText({ a: { b: [{ c: 1 }] } })).not.toContain('[object Object]')
  })
})

describe('ConfigValue', () => {
  it('desenha um registro aninhado como lista de definições', () => {
    const container = render(
      <ConfigValue value={{ terms_review: 'ok', collector_local_test: { status: 'passed' } }} />,
    )

    expect(container.querySelectorAll('dl')).toHaveLength(2)
    expect(container.textContent).toContain('terms_review')
    expect(container.textContent).toContain('status')
    expect(container.textContent).toContain('passed')
    expect(container.textContent).not.toContain('[object Object]')
  })

  it('mostra valores simples em uma linha, sem lista', () => {
    const container = render(<ConfigValue value="acme" />)

    expect(container.querySelector('dl')).toBeNull()
    expect(container.textContent).toBe('acme')
  })

  it('corta a profundidade em texto em vez de recursão sem fim', () => {
    const deep = { a: { b: { c: { d: { e: 'x' } } } } }
    const container = render(<ConfigValue value={deep} />)

    expect(container.textContent).toContain('e: x')
    expect(container.textContent).not.toContain('[object Object]')
  })
})
