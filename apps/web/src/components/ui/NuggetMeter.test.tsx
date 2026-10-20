import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'
import { NuggetMeter } from './NuggetMeter'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const roots: Root[] = []

function render(element: ReactElement) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return container
}

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

describe('NuggetMeter', () => {
  it('desenha pepitas por estado e o texto visível', () => {
    const label = '6 de 9 fatores atendidos, 1 sem dado'
    const container = render(<NuggetMeter met={6} missed={2} unknown={1} label={label} />)
    const meter = container.querySelector(`[role="img"][aria-label="${label}"]`)
    expect(meter).not.toBeNull()
    const visible = [...container.querySelectorAll('span')].find(
      (el) => el.children.length === 0 && el.textContent === label,
    )
    expect(visible?.classList.contains('text-caption')).toBe(true)
    expect(container.querySelectorAll('[data-nugget="met"]')).toHaveLength(6)
    expect(container.querySelectorAll('[data-nugget="missed"]')).toHaveLength(2)
    expect(container.querySelectorAll('[data-nugget="unknown"]')).toHaveLength(1)
  })

  it('missed e unknown começam em zero e a ordem é cheia, vazada, tracejada', () => {
    const container = render(<NuggetMeter met={2} label="2" />)
    expect(container.querySelectorAll('[data-nugget]')).toHaveLength(2)
    const ordered = render(<NuggetMeter met={1} missed={1} unknown={1} label="x" />)
    expect([...ordered.querySelectorAll('[data-nugget]')].map((el) => el.getAttribute('data-nugget'))).toEqual([
      'met',
      'missed',
      'unknown',
    ])
  })
})
