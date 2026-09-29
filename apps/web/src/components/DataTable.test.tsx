import { describe, expect, it } from 'vitest'
import { act } from 'react'
import { DataTable, RowSelect } from './DataTable'
import { render } from './testing'

describe('DataTable', () => {
  it('rola dentro do próprio contêiner, e não na página', () => {
    const container = render(
      <DataTable columns={['Fonte', 'Cobertura']}>
        <tr>
          <td>Greenhouse</td>
          <td>Saudável</td>
        </tr>
      </DataTable>,
    )

    expect(container.firstElementChild?.className).toContain('overflow-x-auto')
  })

  it('associa cada cabeçalho à sua coluna', () => {
    const container = render(
      <DataTable columns={['Status', 'Início']}>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )
    const headers = [...container.querySelectorAll('th')]

    expect(headers.map((header) => header.textContent)).toEqual(['Status', 'Início'])
    expect(headers.every((header) => header.scope === 'col')).toBe(true)
  })

  it('descreve a tabela para leitor de tela quando recebe legenda', () => {
    const container = render(
      <DataTable caption="Execuções recentes" columns={['Status']}>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )
    const caption = container.querySelector('caption')

    expect(caption?.textContent).toBe('Execuções recentes')
    expect(caption?.className).toContain('sr-only')
  })

  it('não inventa legenda quando nenhuma é dada', () => {
    const container = render(
      <DataTable columns={['Status']}>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )

    expect(container.querySelector('caption')).toBeNull()
  })
})

describe('DataTable em tela estreita', () => {
  it('fixa a primeira coluna quando ela é quem nomeia a linha', () => {
    const container = render(
      <DataTable columns={['Fonte', 'Cobertura']} stickyFirstColumn>
        <tr>
          <td>Greenhouse</td>
          <td>Saudável</td>
        </tr>
      </DataTable>,
    )

    expect(container.querySelector('table')?.className).toContain('td:first-child]:sticky')
  })

  it('deixa a tabela solta quando não há coluna a fixar', () => {
    const container = render(
      <DataTable columns={['Status']}>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )

    expect(container.querySelector('table')?.className).not.toContain('sticky')
  })

  it('aceita um id para o botão que a expande apontar', () => {
    const container = render(
      <DataTable columns={['Status']} id="runs-1">
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )

    expect(container.querySelector('#runs-1')).not.toBeNull()
  })
})

describe('DataTable, visual do redesenho', () => {
  it('desenha contêiner com borda e raio de controle, cabeçalho panel sem caixa alta', () => {
    const container = render(
      <DataTable columns={['Status']}>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )
    const head = container.querySelector('thead')

    expect(container.firstElementChild?.className).toContain('rounded-control')
    expect(container.firstElementChild?.className).toContain('border-line')
    expect(head?.className).toContain('bg-panel')
    expect(head?.className).toContain('text-caption')
    expect(head?.className).toContain('text-muted')
    expect(head?.className).not.toContain('uppercase')
  })

  it('garante 44px de linha e divisória line', () => {
    const container = render(
      <DataTable columns={['Status']}>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )
    const classes = container.querySelector('table')?.className ?? ''

    expect(classes).toContain('[&_tbody_td]:h-11')
    expect(classes).toContain('[&_tbody_tr]:border-line')
  })

  it('não tem coluna de seleção por padrão', () => {
    const container = render(
      <DataTable columns={['Status']}>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )

    expect(container.querySelector('input[type="checkbox"]')).toBeNull()
  })

  it('com selectable, oferece "Selecionar todas" rotulado e avisa a escolha', () => {
    const calls: boolean[] = []
    const container = render(
      <DataTable columns={['Status']} onToggleAll={(value) => calls.push(value)} selectable>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )
    const box = container.querySelector<HTMLInputElement>(
      'thead input[aria-label="Selecionar todas"]',
    )

    expect(box).not.toBeNull()
    expect(container.querySelectorAll('th')).toHaveLength(2)
    act(() => box?.click())
    expect(calls).toEqual([true])
  })

  it('marca a seleção parcial como indeterminada', () => {
    const container = render(
      <DataTable columns={['Status']} selectable someSelected>
        <tr>
          <td>Sucesso</td>
        </tr>
      </DataTable>,
    )

    expect(container.querySelector<HTMLInputElement>('thead input')?.indeterminate).toBe(true)
  })

  it('RowSelect exige rótulo que nomeia a linha', () => {
    const container = render(
      <RowSelect checked={false} label="Selecionar Acme" onChange={() => {}} />,
    )

    expect(container.querySelector('input')?.getAttribute('aria-label')).toBe('Selecionar Acme')
  })
})
