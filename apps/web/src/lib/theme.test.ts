import { afterEach, describe, expect, it, vi } from 'vitest'
import { applyThemePreference, readThemePreference, writeThemePreference } from './theme'

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
})

describe('theme preference', () => {
  it('cai para system quando localStorage lança', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(readThemePreference()).toBe('system')
  })

  it('valor inválido vira system e valor salvo é lido', () => {
    localStorage.setItem('bateia-theme', 'neon')
    expect(readThemePreference()).toBe('system')
    writeThemePreference('dark')
    expect(localStorage.getItem('bateia-theme')).toBe('dark')
    expect(readThemePreference()).toBe('dark')
  })

  it('escrever não lança quando localStorage lança', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(() => writeThemePreference('light')).not.toThrow()
  })

  it('system remove data-theme; dark define', () => {
    const root = document.createElement('html')
    applyThemePreference('dark', root)
    expect(root.dataset.theme).toBe('dark')
    applyThemePreference('system', root)
    expect(root.hasAttribute('data-theme')).toBe(false)
  })
})
