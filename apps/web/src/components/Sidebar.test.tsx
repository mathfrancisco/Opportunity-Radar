import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar, type NavigationPath } from './Sidebar'
import { render } from './testing'

function renderSidebar(current?: NavigationPath, isOwner = false) {
  return render(
    <MemoryRouter>
      <Sidebar current={current} isOwner={isOwner} />
    </MemoryRouter>,
  )
}

describe('Sidebar', () => {
  it('expõe navegação padrão com Visão geral, Inbox, Pipeline e Perfil', () => {
    const container = renderSidebar()
    const nav = container.querySelector('nav')
    const groups = [...container.querySelectorAll('nav ul[aria-labelledby]')].map((list) => [
      container.querySelector(`#${list.getAttribute('aria-labelledby')}`)?.textContent,
      [...list.querySelectorAll('a')].map((a) => a.textContent),
    ])

    expect(nav?.getAttribute('aria-label')).toBe('Navegação principal')
    expect(groups).toEqual([
      ['Decidir', ['Visão geral', 'Inbox', 'Pipeline']],
      ['Operar', ['Perfil']],
    ])
  })

  it('expõe itens adicionais apenas para owner', () => {
    const container = renderSidebar(undefined, true)
    const items = [...container.querySelectorAll('nav a')].map((link) => link.textContent)

    expect(items).toEqual(['Visão geral', 'Inbox', 'Pipeline', 'Empresas', 'Fontes', 'Homologação', 'Perfil', 'Status'])
  })

  it('marca só o item atual, com fundo, peso, marcador e aria-current', () => {
    const container = renderSidebar('/sources', true)
    const active = container.querySelectorAll('nav [aria-current="page"]')

    expect(active).toHaveLength(1)
    expect(active[0].textContent).toBe('Fontes')
    expect(active[0].className).toContain('bg-surface')
    expect(active[0].className).toContain('font-semibold')
    expect(active[0].className).toContain('--color-accent')
  })

  it('marca a fila de homologação sem marcar Fontes', () => {
    const container = renderSidebar('/sources/homologation-queue', true)
    const active = container.querySelectorAll('nav [aria-current="page"]')

    expect(active).toHaveLength(1)
    expect(active[0].textContent).toBe('Homologação')
    expect(active[0].getAttribute('href')).toBe('/sources/homologation-queue')
  })

  it('não marca nada fora da navegação', () => {
    expect(renderSidebar().querySelector('nav [aria-current]')).toBeNull()
  })

  it('esconde o ícone do leitor de tela', () => {
    const container = renderSidebar('/sources')

    for (const link of container.querySelectorAll('nav a')) {
      expect(link.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    }
  })

  it('mostra a marca, a nota de privacidade e o seletor de tema', () => {
    const container = renderSidebar()

    expect(container.querySelector('[role="img"][aria-label="Bateia"]')).not.toBeNull()
    expect(container.textContent).toContain('Nenhuma empresa vê seu perfil aqui.')
    expect(container.querySelector('[role="group"][aria-label="Tema"]')).not.toBeNull()
    for (const label of container.querySelectorAll('nav p')) {
      expect(label.className).toContain('font-semibold')
      expect(label.className).not.toMatch(/uppercase|tracking-/)
    }
  })
})
