import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { PageShell } from './PageShell'
import { render } from './testing'

function renderShell(current?: '/sources') {
  return render(
    <MemoryRouter>
      <PageShell current={current} eyebrow="Operação" title="Fontes">
        <p>conteúdo</p>
      </PageShell>
    </MemoryRouter>,
  )
}

describe('PageShell', () => {
  it('agrupa a navegação pelo que cada tela serve', () => {
    const container = renderShell('/sources')
    const groups = [...container.querySelectorAll('nav ul[aria-labelledby]')].map((list) => {
      const label = container.querySelector(`#${list.getAttribute('aria-labelledby')}`)
      return [label?.textContent, [...list.querySelectorAll('a')].map((a) => a.textContent)]
    })

    expect(groups).toEqual([
      ['Dia a dia', ['Visão geral', 'Oportunidades', 'Candidaturas']],
      ['Catálogo', ['Empresas', 'Fontes', 'Perfil']],
      ['Diagnóstico', ['Status']],
    ])
  })

  it('marca uma única seção ativa, sem depender de foco ou cursor', () => {
    const container = renderShell('/sources')
    const active = container.querySelectorAll('nav [aria-current="page"]')

    expect(active).toHaveLength(1)
    expect(active[0].textContent).toBe('Fontes')
    expect(active[0].className).toContain('bg-ink')
  })

  it('não marca nada numa página que não está na navegação', () => {
    const container = renderShell()

    expect(container.querySelector('nav [aria-current]')).toBeNull()
  })

  it('dá a cada item ícone e rótulo, e esconde o ícone do leitor de tela', () => {
    const container = renderShell('/sources')

    for (const link of container.querySelectorAll('nav a')) {
      const icon = link.querySelector('svg')
      expect(icon?.getAttribute('aria-hidden')).toBe('true')
      expect(link.textContent?.trim()).not.toBe('')
    }
  })

  it('mantém o link de pular ao conteúdo como primeiro alvo de tabulação', () => {
    const container = renderShell('/sources')
    const first = container.querySelector('a')

    expect(first?.getAttribute('href')).toBe('#conteudo')
    expect(container.querySelector('#conteudo')).not.toBeNull()
  })
})
