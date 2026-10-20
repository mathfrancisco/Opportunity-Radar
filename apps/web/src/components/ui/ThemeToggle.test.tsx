import { act, type ReactElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'
import { ThemeToggle } from './ThemeToggle'

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
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeToggle', () => {
  it('oferece Sistema, Claro e Escuro e aplica a escolha', () => {
    const container = render(<ThemeToggle />)
    expect(container.querySelector('[role="group"][aria-label="Tema"]')).not.toBeNull()
    const buttons = [...container.querySelectorAll('button')]
    expect(buttons.map((b) => b.textContent)).toEqual(['Sistema', 'Claro', 'Escuro'])
    expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false', 'false'])

    expect(buttons[0].className).toContain('border-control-line')
    expect(buttons[1].className).toContain('border-transparent')

    act(() => buttons[2].click())

    expect(buttons[2].className).toContain('border-control-line')
    expect(buttons[0].className).toContain('border-transparent')

    expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'false', 'true'])
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('bateia-theme')).toBe('dark')
  })

  it('lê a preferência salva', () => {
    localStorage.setItem('bateia-theme', 'light')
    const container = render(<ThemeToggle />)
    expect(container.querySelectorAll('button')[1].getAttribute('aria-pressed')).toBe('true')
  })
})
