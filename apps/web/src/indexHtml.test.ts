import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'

const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8')
const scriptMatch = /<script>([\s\S]*?)<\/script>/.exec(html)

afterEach(() => {
  vi.restoreAllMocks()
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('index.html theme bootstrap', () => {
  it('tem script inline antes do manifest, lendo bateia-theme dentro de try/catch', () => {
    expect(scriptMatch).not.toBeNull()
    const body = scriptMatch![1]
    expect(html.indexOf('<script>')).toBeLessThan(html.indexOf('<link rel="manifest"'))
    expect(body).toContain('bateia-theme')
    expect(body).toMatch(/try\s*\{[\s\S]*\}\s*catch/)
    expect(body).toContain("'light'")
    expect(body).toContain("'dark'")
  })

  it('aplica data-theme só para light e dark', () => {
    const run = () => new Function(scriptMatch![1])()
    localStorage.setItem('bateia-theme', 'dark')
    run()
    expect(document.documentElement.dataset.theme).toBe('dark')
    document.documentElement.removeAttribute('data-theme')
    localStorage.setItem('bateia-theme', 'system')
    run()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
    localStorage.setItem('bateia-theme', 'neon')
    run()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it('não lança nem define data-theme quando localStorage lança', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    expect(() => new Function(scriptMatch![1])()).not.toThrow()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })
})
