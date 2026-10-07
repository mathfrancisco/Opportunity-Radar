import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar, type NavigationPath } from './Sidebar'
import { render } from './testing'

function renderSidebar(current?: NavigationPath) {
  return render(
    <MemoryRouter>
      <Sidebar current={current} />
    </MemoryRouter>,
  )
}

describe('Sidebar', () => {
  it('expõe uma navegação principal com os três grupos e os oito itens', () => {
    const container = renderSidebar('/sources')
    const nav = container.querySelector('nav')
    const groups = [...container.querySelectorAll('nav ul[aria-labelledby]')].map((list) => [
      container.querySelector(`#${list.getAttribute('aria-labelledby')}`)?.textContent,
      [...list.querySelectorAll('a')].map((a) => a.textContent),
    ])

    expect(nav?.getAttribute('aria-label')).toBe('Navegação principal')
    expect(groups).toEqual([
      ['Decidir', ['Visão geral', 'Inbox', 'Pipeline']],
      ['Pesquisar', ['Empresas']],
      ['Operar', ['Fontes', 'Homologação', 'Perfil', 'Status']],
    ])
  })

  it('marca só o item atual, com fundo, peso, marcador e aria-current', () => {
    const container = renderSidebar('/sources')
    const active = container.querySelectorAll('nav [aria-current="page"]')

    expect(active).toHaveLength(1)
    expect(active[0].textContent).toBe('Fontes')
    expect(active[0].className).toContain('bg-surface')
    expect(active[0].className).toContain('font-semibold')
    expect(active[0].className).toContain('--color-accent')
  })

  it('marca a fila de homologação sem marcar Fontes', () => {
    const container = renderSidebar('/sources/homologation-queue')
    const active = container.querySelectorAll('nav [aria-current="page"]')

    expect(active).toHaveLength(1)
    expect(active[0].textContent).toBe('Homologação')
    expect(active[0].getAttribute('href')).toBe('/sources/homologation-queue')
  })

  it('não marca nada fora da navegação', () => {
    expect(renderSidebar().querySelector('nav [aria-current]')).toBeNull()
  })

  it('esconde o ícone do leitor de tela e mantém o logotipo petróleo com glifo claro', () => {
    const container = renderSidebar('/sources')

    for (const link of container.querySelectorAll('nav a')) {
      expect(link.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    }
    expect(container.querySelector('.bg-brand.text-surface')).not.toBeNull()
  })
})
