import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  applyThemePreference,
  readThemePreference,
  subscribeThemePreference,
  writeThemePreference,
} from './theme'

const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')
const metaTags = html.match(/<meta name="theme-color"[^>]*>/g) ?? []

function themeColors() {
  return [...document.querySelectorAll('meta[name="theme-color"]')].map((m) => ({
    media: m.getAttribute('media'),
    content: m.getAttribute('content')?.replace('#', ''),
  }))
}

function declared(media: string) {
  const tag = metaTags.find((t) => t.includes(media)) ?? ''
  return /content="#?([^"]+)"/.exec(tag)?.[1]
}

beforeEach(() => {
  document.head.insertAdjacentHTML('beforeend', metaTags.join(''))
})

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  document.head.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.remove())
  document.documentElement.removeAttribute('data-theme')
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

  it('ajusta as duas metas theme-color conforme a preferência', () => {
    const light = declared('light')
    const dark = declared('dark')
    expect(light).toBeTruthy()
    expect(dark).toBeTruthy()
    expect(light).not.toBe(dark)

    applyThemePreference('dark')
    expect(themeColors().map((c) => c.content)).toEqual([dark, dark])
    applyThemePreference('light')
    expect(themeColors().map((c) => c.content)).toEqual([light, light])
    applyThemePreference('system')
    expect(themeColors()).toEqual([
      { media: '(prefers-color-scheme: light)', content: light },
      { media: '(prefers-color-scheme: dark)', content: dark },
    ])
  })

  it('writeThemePreference notifica os assinantes até cancelar', () => {
    const listener = vi.fn()
    const unsubscribe = subscribeThemePreference(listener)
    writeThemePreference('dark')
    expect(listener).toHaveBeenCalledTimes(1)
    unsubscribe()
    writeThemePreference('light')
    expect(listener).toHaveBeenCalledTimes(1)
  })
})
