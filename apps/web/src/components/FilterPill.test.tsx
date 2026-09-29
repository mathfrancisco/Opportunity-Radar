import { act } from 'react'
import { describe, expect, it } from 'vitest'
import { FilterBar } from './FilterBar'
import { FilterPill } from './FilterPill'
import { SearchInput } from './SearchInput'
import { render } from './testing'

const options = [
  { value: '', label: 'Todas' },
  { value: 'apply', label: 'Candidatar' },
  { value: 'skip', label: 'Descartar' },
]

function pill(value: string, onChange: (value: string) => void = () => {}) {
  return render(
    <FilterPill id="verdict" label="Decisão" onChange={onChange} options={options} value={value} />,
  )
}

function type(input: HTMLInputElement, text: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  act(() => {
    setter?.call(input, text)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

describe('FilterPill', () => {
  it('mostra o rótulo e nomeia o select por ele', () => {
    const container = pill('')
    const select = container.querySelector<HTMLSelectElement>('select')
    const label = container.querySelector('label')

    expect(label?.textContent).toBe('Decisão')
    expect(label?.htmlFor).toBe('verdict')
    expect(select?.id).toBe('verdict')
    expect(select?.labels?.[0]).toBe(label)
  })

  it('esconde ícone e chevron da árvore de acessibilidade', () => {
    const container = pill('')

    expect(container.querySelectorAll(':scope > div > span[aria-hidden="true"]')).toHaveLength(2)
  })

  it('avisa o novo valor ao trocar a opção', () => {
    const chosen: string[] = []
    const container = pill('', (value) => chosen.push(value))
    const select = container.querySelector<HTMLSelectElement>('select')

    act(() => {
      if (select) select.value = 'skip'
      select?.dispatchEvent(new Event('change', { bubbles: true }))
    })

    expect(chosen).toEqual(['skip'])
  })

  it('só fica ativa quando o valor difere do padrão', () => {
    const idle = pill('').firstElementChild
    const active = pill('apply').firstElementChild

    expect(idle?.getAttribute('data-active')).toBe('false')
    expect(idle?.className).toContain('border-line-strong')
    expect(active?.getAttribute('data-active')).toBe('true')
    expect(active?.className).toContain('border-ink')
    expect(active?.querySelector('label')?.className).toContain('font-semibold')
  })

  it('respeita um padrão que não é vazio', () => {
    const container = render(
      <FilterPill
        defaultValue="apply"
        id="verdict"
        label="Decisão"
        onChange={() => {}}
        options={options}
        value="apply"
      />,
    )

    expect(container.firstElementChild?.getAttribute('data-active')).toBe('false')
  })
})

describe('SearchInput', () => {
  function search(onSubmit: () => void = () => {}, onChange: (v: string) => void = () => {}) {
    return render(
      <SearchInput
        id="q"
        label="Buscar vagas"
        onChange={onChange}
        onSubmit={onSubmit}
        placeholder="Título ou empresa"
        value="rust"
      />,
    )
  }

  it('é uma busca rotulada, com a lupa como botão "Buscar" só para leitor de tela', () => {
    const container = search()
    const button = container.querySelector('button')

    expect(container.querySelector('form')?.getAttribute('role')).toBe('search')
    expect(container.querySelector('input')?.labels?.[0].textContent).toBe('Buscar vagas')
    expect(button?.type).toBe('submit')
    expect(button?.textContent).toBe('Buscar')
    expect(button?.querySelector('.sr-only')?.textContent).toBe('Buscar')
    expect(button?.querySelector('svg')?.getAttribute('aria-hidden')).toBe('true')
  })

  it('envia ao apertar Enter no campo (envio do formulário) sem recarregar a página', () => {
    let submits = 0
    const container = search(() => (submits += 1))
    const form = container.querySelector('form')
    const event = new Event('submit', { bubbles: true, cancelable: true })

    act(() => {
      form?.dispatchEvent(event)
    })

    expect(submits).toBe(1)
    expect(event.defaultPrevented).toBe(true)
  })

  it('envia ao clicar na lupa', () => {
    let submits = 0
    const container = search(() => (submits += 1))

    act(() => container.querySelector('button')?.click())

    expect(submits).toBe(1)
  })

  it('repassa o que é digitado', () => {
    const typed: string[] = []
    const container = search(() => {}, (value) => typed.push(value))
    const input = container.querySelector<HTMLInputElement>('input')

    if (input) type(input, 'go')

    expect(typed).toEqual(['go'])
  })
})

describe('FilterBar', () => {
  it('põe as pílulas à esquerda e a busca à direita, com quebra de linha', () => {
    const container = render(
      <FilterBar search={<span data-testid="search">busca</span>}>
        <span>pílula</span>
      </FilterBar>,
    )
    const bar = container.firstElementChild
    const search = container.querySelector('[data-testid="search"]')?.parentElement

    expect(bar?.className).toContain('flex-wrap')
    expect(bar?.querySelector('[role="group"]')?.textContent).toBe('pílula')
    expect(search?.className).toContain('md:ml-auto')
    expect(search?.className).toContain('w-full')
  })

  it('não desenha o espaço da busca quando não há busca', () => {
    const container = render(
      <FilterBar>
        <span>pílula</span>
      </FilterBar>,
    )

    expect(container.firstElementChild?.children).toHaveLength(1)
  })
})
