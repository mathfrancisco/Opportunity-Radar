import { describe, expect, it, vi } from 'vitest'
import { ConflictNotice, EmptyState, ErrorState, LoadingState } from './states'
import { render } from './testing'

describe('estados da interface', () => {
  it('anuncia carregamento como informação, não como alerta', () => {
    const container = render(<LoadingState>Carregando fontes…</LoadingState>)
    const block = container.firstElementChild

    expect(block?.getAttribute('role')).toBe('status')
    expect(block?.textContent).toBe('Carregando fontes…')
  })

  it('anuncia o vazio sem tratá-lo como falha', () => {
    const container = render(<EmptyState>Nenhuma fonte cadastrada.</EmptyState>)
    const block = container.firstElementChild

    expect(block?.getAttribute('role')).toBe('status')
    expect(block?.className).toContain('border-dashed')
    expect(block?.className).not.toContain('danger')
  })

  it('anuncia erro como alerta e oferece nova tentativa', () => {
    const retry = vi.fn()
    const container = render(
      <ErrorState onRetry={retry}>Não foi possível carregar as fontes.</ErrorState>,
    )
    const block = container.firstElementChild

    expect(block?.getAttribute('role')).toBe('alert')
    container.querySelector('button')?.click()
    expect(retry).toHaveBeenCalledOnce()
  })

  it('não oferece botão quando não há o que tentar de novo', () => {
    const container = render(<ErrorState>Falha sem recuperação.</ErrorState>)

    expect(container.querySelector('button')).toBeNull()
  })

  it('separa conflito de falha, e oferece reler em vez de repetir', () => {
    const reload = vi.fn()
    const container = render(
      <ConflictNotice onReload={reload}>O perfil mudou enquanto você editava.</ConflictNotice>,
    )
    const block = container.firstElementChild
    const button = container.querySelector('button')

    expect(block?.getAttribute('role')).toBe('alert')
    // Tom de atenção, não de erro: ninguém quebrou nada, a versão é que avançou.
    expect(block?.className).toContain('warning')
    expect(button?.textContent).toBe('Recarregar o registro')
    button?.click()
    expect(reload).toHaveBeenCalledOnce()
  })
})
