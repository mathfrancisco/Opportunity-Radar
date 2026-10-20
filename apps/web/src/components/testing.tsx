import { type ReactElement } from 'react'
import { act } from 'react'
import { createRoot } from 'react-dom/client'

/**
 * Renders a component into a real DOM node and hands back the container.
 *
 * Deliberately the smallest possible harness: these are presentational components, and the
 * assertions are about the markup they produce, not about a testing library's idea of it.
 */
export function render(element: ReactElement): HTMLElement {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(element)
  })
  return container
}

/**
 * The text a person reads on a screen: everything except what sits inside `<details>`.
 *
 * Technical codes are allowed only in a collapsed "Detalhe técnico", so the tests assert
 * that none shows up here.
 */
export function visibleTextOutsideDetails(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement
  clone.querySelectorAll('details').forEach((details) => details.remove())
  return clone.textContent ?? ''
}
