import { describe, expect, it } from 'vitest'
import { DataTable } from './DataTable'
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
