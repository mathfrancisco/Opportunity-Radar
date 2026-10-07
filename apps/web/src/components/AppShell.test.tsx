import { act } from 'react'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { AppShell } from './AppShell'
import { render } from './testing'

function renderShell() {
  return render(
    <MemoryRouter>
      <AppShell current="/sources" description="Fontes ativas" title="Fontes">
        <p>conteúdo</p>
      </AppShell>
    </MemoryRouter>,
  )
}

function menuButton(container: HTMLElement) {
  return container.querySelector<HTMLButtonElement>('button[aria-controls]')!
}

describe('AppShell', () => {
  it('põe o link de pular como primeiro alvo de tabulação', () => {
    const container = renderShell()
    const tabbable = container.querySelectorAll('a[href], button')

    expect(tabbable[0].getAttribute('href')).toBe('#conteudo')
    expect(container.querySelector('#conteudo')).not.toBeNull()
  })

  it('renderiza título, descrição e rodapé sem sombra no painel', () => {
    const container = render(
      <MemoryRouter>
        <AppShell footer={<span>rodapé</span>} title="Fontes">
          <p>conteúdo</p>
        </AppShell>
      </MemoryRouter>,
    )

    expect(container.querySelector('h1')?.textContent).toBe('Fontes')
    expect(container.querySelector('footer')?.textContent).toBe('rodapé')
    expect(container.innerHTML).not.toContain('shadow-shell')
  })

  it('desenha o link de volta acima do título e o eyebrow só quando dado', () => {
    const container = render(
      <MemoryRouter>
        <AppShell back={<a href="/inbox">Voltar</a>} eyebrow="Oportunidade" title="Vaga">
          <p>conteúdo</p>
        </AppShell>
      </MemoryRouter>,
    )
    const back = container.querySelector('a[href="/inbox"]') as HTMLElement
    const h1 = container.querySelector('h1') as HTMLElement
    expect(back.compareDocumentPosition(h1) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(container.querySelector('header p')?.textContent).toBe('Oportunidade')
    expect(renderShell().querySelector('header p')?.textContent).toBe('Fontes ativas')
  })

  it('abre a gaveta pelo botão, com aria-expanded e aria-controls', () => {
    const container = renderShell()
    const button = menuButton(container)

    expect(button.getAttribute('aria-expanded')).toBe('false')
    expect(container.querySelector(`#${button.getAttribute('aria-controls')}`)).not.toBeNull()
    expect(container.querySelector('aside')?.className).toContain('hidden')

    act(() => button.click())

    expect(button.getAttribute('aria-expanded')).toBe('true')
    expect(container.querySelector('aside')?.className).toContain('fixed')
  })

  it('fecha a gaveta com Esc e devolve o foco ao botão', () => {
    const container = renderShell()
    const button = menuButton(container)
    act(() => button.click())
    container.querySelector<HTMLElement>('aside a')?.focus()

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    })

    expect(button.getAttribute('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(button)
  })

  it('fecha a gaveta ao seguir um link', () => {
    const container = renderShell()
    const button = menuButton(container)
    act(() => button.click())

    act(() => container.querySelector<HTMLElement>('aside nav a')?.click())

    expect(button.getAttribute('aria-expanded')).toBe('false')
  })
})
