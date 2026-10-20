import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'
import { BrandMark, BrandSymbol } from './BrandMark'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const roots: Root[] = []

function render(element: ReactElement) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(element))
  return { container }
}

afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

describe('BrandMark', () => {
  it('desenha três anéis e uma pepita na posição fixa', () => {
    const { container } = render(<BrandSymbol />)
    expect(container.querySelectorAll('circle[fill="none"]')).toHaveLength(3)
    const nugget = container.querySelector('circle.fill-nugget')
    expect(nugget?.getAttribute('cx')).toBe('21.5')
    expect(nugget?.getAttribute('cy')).toBe('11')
    expect(container.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })

  it('o wordmark é lido como Bateia', () => {
    const { container } = render(<BrandMark />)
    const word = container.querySelector('.font-display')
    expect(word?.textContent).toBe('bateia')
    expect(word?.classList.contains('text-2xl')).toBe(true)
    expect(container.querySelector('[role="img"][aria-label="Bateia"]')).not.toBeNull()
  })
})
