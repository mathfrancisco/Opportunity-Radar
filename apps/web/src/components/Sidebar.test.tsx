import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { render } from './testing'

function renderSidebar(current?: '/sources') {
  return render(
    <MemoryRouter>
      <Sidebar current={current} />
    </MemoryRouter>,
  )
}

describe('Sidebar', () => {
  it('expõe uma navegação principal com os três grupos e os sete itens', () => {
    const container = renderSidebar('/sources')
    const nav = container.querySelector('nav')
    const groups = [...container.querySelectorAll('nav ul[aria-labelledby]')].map((list) => [
      container.querySelector(`#${list.getAttribute('aria-labelledby')}`)?.textContent,
      [...list.querySelectorAll('a')].map((a) => a.textContent),
    ])

    expect(nav?.getAttribute('aria-label')).toBe('Navegação principal')
    expect(groups).toEqual([
      ['Dia a dia', ['Visão geral', 'Oportunidades', 'Candidaturas']],
      ['Catálogo', ['Empresas', 'Fontes', 'Perfil']],
      ['Diagnóstico', ['Status']],
    ])
  })

  it('marca só o item atual, como pílula branca, com aria-current', () => {
    const container = renderSidebar('/sources')
    const active = container.querySelectorAll('nav [aria-current="page"]')

    expect(active).toHaveLength(1)
    expect(active[0].textContent).toBe('Fontes')
    expect(active[0].className).toContain('bg-surface')
  })

  it('não marca nada fora da navegação', () => {
    expect(renderSidebar().querySelector('nav [aria-current]')).toBeNull()
  })

  it('esconde o ícone do leitor de tela e mantém o logotipo na cor da marca', () => {
    const container = renderSidebar('/sources')

    for (const link of container.querySelectorAll('nav a')) {
      expect(link.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
    }
    expect(container.querySelector('.bg-brand')).not.toBeNull()
  })
})
