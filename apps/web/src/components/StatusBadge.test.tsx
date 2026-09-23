import { describe, expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'
import { render } from './testing'
import { coverageLabels, coverageTones } from '../features/sources/states'

const labels = { SUCCEEDED: 'Sucesso', FAILED: 'Falhou' }
const tones = { SUCCEEDED: 'bg-success-surface', FAILED: 'bg-danger-surface' }

describe('StatusBadge', () => {
  it('traduz e colore um estado conhecido', () => {
    const container = render(<StatusBadge labels={labels} tones={tones} value="SUCCEEDED" />)
    const badge = container.querySelector('span')

    expect(badge?.textContent).toBe('Sucesso')
    expect(badge?.className).toContain('bg-success-surface')
  })

  it('mostra o próprio código quando o estado não tem tradução', () => {
    const container = render(<StatusBadge labels={labels} tones={tones} value="QUARANTINED" />)
    const badge = container.querySelector('span')

    // Inventar "desconhecido" esconderia justamente o caso que vale ler.
    expect(badge?.textContent).toBe('QUARANTINED')
    expect(badge?.className).toContain('bg-canvas')
  })

  it('distingue estado ausente de estado desconhecido', () => {
    const container = render(
      <StatusBadge absent="Nunca executada" labels={labels} tones={tones} value={null} />,
    )
    const badge = container.querySelector('span')

    expect(badge?.textContent).toBe('Nunca executada')
    expect(badge?.className).toContain('border-dashed')
  })

  it('usa um texto padrão quando a ausência não é nomeada', () => {
    const container = render(<StatusBadge labels={labels} tones={tones} value={null} />)

    expect(container.querySelector('span')?.textContent).toBe('Sem registro')
  })

  it('mantém sucesso sem vagas distinguível de fonte que não executou', () => {
    const empty = render(
      <StatusBadge labels={coverageLabels} tones={coverageTones} value="SUCCEEDED_ZERO" />,
    )
    const idle = render(
      <StatusBadge labels={coverageLabels} tones={coverageTones} value="NOT_RUN" />,
    )

    expect(empty.textContent).toBe('Sucesso sem vagas')
    expect(idle.textContent).toBe('Não executou na janela')
  })
})
