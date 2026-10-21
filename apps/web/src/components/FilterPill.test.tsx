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
  it('desabilita o select e liga a descrição acessível quando disabled', () => {
    const container = render(
      <FilterPill
        description="Explicação do estado"
        disabled
        id="verdict"
        label="Decisão"
        onChange={() => {}}
        options={options}
        value=""
      />,
    )
    const select = container.querySelector<HTMLSelectElement>('select')
    const describedBy = select?.getAttribute('aria-describedby') ?? ''

    expect(select?.disabled).toBe(true)
    expect(describedBy).not.toBe('')
    expect(document.getElementById(describedBy)?.textContent).toBe('Explicação do estado')
  })

  it('não liga descrição nem desabilita por padrão', () => {
    const container = pill('')
    const select = container.querySelector<HTMLSelectElement>('select')

    expect(select?.disabled).toBe(false)
    expect(select?.hasAttribute('aria-describedby')).toBe(false)
  })

  it('no formato de campo usa um combobox temático rotulado e ocupa toda a largura disponível', () => {
    const container = render(
      <FilterPill
        className="w-full"
        id="verdict"
        label="Decisão"
        onChange={() => {}}
        options={options}
        value="apply"
        variant="field"
      />,
    )
    const trigger = container.querySelector<HTMLButtonElement>('#verdict')
    const label = container.querySelector('#verdict-label')

    expect(label?.textContent).toBe('Decisão')
    expect(trigger?.getAttribute('role')).toBe('combobox')
    expect(trigger?.getAttribute('aria-expanded')).toBe('false')
    expect(trigger?.className).toContain('w-full')
    expect(trigger?.className).toContain('border-ink')
    expect(trigger?.className).toContain('max-md:h-11')
    expect(container.querySelector('select')).toBeNull()
    expect(container.firstElementChild?.className).toContain('w-full')
    expect(container.firstElementChild?.getAttribute('data-active')).toBe('true')
  })

  it('no formato de campo deixa o estado desabilitado explícito', () => {
    const container = render(
      <FilterPill
        description="Explicação do estado"
        disabled
        id="verdict"
        label="Decisão"
        onChange={() => {}}
        options={options}
        value=""
        variant="field"
      />,
    )
    const trigger = container.querySelector<HTMLButtonElement>('#verdict')
    const describedBy = trigger?.getAttribute('aria-describedby') ?? ''

    expect(container.firstElementChild?.getAttribute('data-disabled')).toBe('true')
    expect(trigger?.disabled).toBe(true)
    expect(trigger?.className).toContain('cursor-not-allowed')
    expect(document.getElementById(describedBy)?.textContent).toBe('Explicação do estado')
  })

  it('no formato de campo informa a opção escolhida', () => {
    const chosen: string[] = []
    const container = render(
      <FilterPill
        id="verdict"
        label="Decisão"
        onChange={(value) => chosen.push(value)}
        options={options}
        value=""
        variant="field"
      />,
    )
    const trigger = container.querySelector<HTMLButtonElement>('#verdict')

    act(() => {
      trigger?.click()
    })
    expect(trigger?.getAttribute('aria-expanded')).toBe('true')
    const option = Array.from(container.querySelectorAll('[role="option"]')).find(
      (candidate) => candidate.textContent?.includes('Descartar'),
    ) as HTMLButtonElement
    act(() => option.click())

    expect(chosen).toEqual(['skip'])
  })

  it('ancora a lista aberta no botão, mesmo quando a raiz inclui a lista', () => {
    const container = render(<FilterPill id="verdict" label="Decisão" onChange={() => {}} options={options} value="" variant="field" />)
    const trigger = container.querySelector<HTMLButtonElement>('#verdict')

    Object.defineProperty(trigger, 'getBoundingClientRect', {
      value: () => ({ bottom: 200, height: 36, left: 40, right: 240, top: 164, width: 200 }),
    })
    Object.defineProperty(container.firstElementChild, 'getBoundingClientRect', {
      value: () => ({ bottom: 506, height: 342, left: 40, right: 240, top: 164, width: 200 }),
    })

    act(() => trigger?.click())

    expect(container.querySelector<HTMLElement>('[role="listbox"]')?.style.top).toBe('204px')
  })

  it('navega e escolhe com teclado, fecha com Escape e expõe a opção ativa', () => {
    const chosen: string[] = []
    const container = render(<FilterPill id="verdict" label="Decisão" onChange={(value) => chosen.push(value)} options={options} value="" variant="field" />)
    const trigger = container.querySelector<HTMLButtonElement>('#verdict')
    act(() => trigger?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })))
    expect(trigger?.getAttribute('aria-expanded')).toBe('true')
    expect(trigger?.getAttribute('aria-activedescendant')).toContain('option-1')
    act(() => trigger?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
    expect(chosen).toEqual(['apply'])
    act(() => trigger?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    expect(trigger?.getAttribute('aria-expanded')).toBe('false')
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

  it('alinha os campos do toolbar pela base', () => {
    const container = render(
      <FilterBar variant="toolbar">
        <span>pílula</span>
      </FilterBar>,
    )

    expect(container.firstElementChild?.className).toContain('items-end')
    expect(container.querySelector('[role="group"]')?.className).toContain('items-end')
  })
})
