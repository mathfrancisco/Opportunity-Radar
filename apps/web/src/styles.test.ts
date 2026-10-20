import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const css = readFileSync('src/styles.css', 'utf8')

/*
 * Lê os valores de `@theme` em styles.css e mede o contraste WCAG 2.x de cada par
 * documentado em docs/35-design-tokens.md. Falha se um token for trocado por um valor
 * que reprova: o contraste deixa de ser só uma tabela e vira regressão.
 */
function token(name: string): string {
  const match = new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6})\\s*;`).exec(css)
  if (!match) throw new Error(`token --color-${name} não encontrado em styles.css`)
  return match[1]
}

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2)
}

function contrastOf(fgHex: string, bgHex: string): number {
  const [a, b] = [luminance(fgHex), luminance(bgHex)].sort((x, y) => y - x)
  return (a + 0.05) / (b + 0.05)
}

function contrast(fg: string, bg: string): number {
  return contrastOf(token(fg), token(bg))
}

function parseColors(block: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const m of block.matchAll(/--color-([a-z-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim()
  return out
}

function dataThemeDarkText(): string {
  const m = /:root\[data-theme="dark"\]\s*{([^}]*)}/.exec(css)
  if (!m) throw new Error('bloco :root[data-theme="dark"] não encontrado em styles.css')
  return m[1]
}

function mediaDarkText(): string {
  const m =
    /@media \(prefers-color-scheme: dark\)\s*{\s*:root:not\(\[data-theme="light"\]\)\s*{([^}]*)}/.exec(css)
  if (!m) throw new Error('bloco @media (prefers-color-scheme: dark) não encontrado em styles.css')
  return m[1]
}

function dataThemeDarkBlock(): Record<string, string> {
  return parseColors(dataThemeDarkText())
}

function mediaDarkBlock(): Record<string, string> {
  return parseColors(mediaDarkText())
}

function darkToken(name: string): string {
  const value = dataThemeDarkBlock()[name]
  if (!value) throw new Error(`token --color-${name} não encontrado no bloco escuro`)
  return value
}

const TEXT_PAIRS: Array<[string, string]> = [
  ['ink', 'sidebar'],
  ['subtle', 'sidebar'],
  ['muted', 'sidebar'],
  ['accent-ink', 'sidebar'],
  ['subtle', 'panel'],
  ['accent-ink', 'panel'],
  ['accent-ink', 'accent-surface'],
  ['ink', 'accent-surface'],
  ['muted', 'accent-surface'],
  ['neutral-ink', 'surface'],
  ['ink', 'canvas'],
  ['ink', 'surface'],
  ['ink', 'raised'],
  ['ink', 'panel'],
  ['subtle', 'surface'],
  ['subtle', 'canvas'],
  ['muted', 'surface'],
  ['muted', 'canvas'],
  ['muted', 'panel'],
  ['neutral-ink', 'canvas'],
  ['accent-ink', 'surface'],
  ['accent-ink', 'canvas'],
  ['success-ink', 'success-surface'],
  ['success-ink', 'success-surface-soft'],
  ['success-ink-strong', 'success-surface-strong'],
  ['warning-ink', 'warning-surface'],
  ['warning-ink-strong', 'warning-surface-strong'],
  ['danger-ink', 'danger-surface'],
  ['danger-ink', 'danger-surface-strong'],
  ['info-ink', 'info-surface'],
  ['surface', 'ink'],
  ['surface', 'ink-hover'],
  ['surface', 'accent'],
  ['surface', 'accent-hover'],
  ['surface', 'brand'],
  ['nugget-ink', 'nugget-surface'],
  ['nugget-ink', 'surface'],
  ['nugget-ink', 'canvas'],
]

const CONTROL_PAIRS: Array<[string, string]> = [
  ['control-line', 'surface'],
  ['control-line', 'canvas'],
  ['control-line', 'sidebar'],
  ['accent', 'surface'],
  ['ink', 'surface'],
  // Anel de foco (:focus-visible usa `accent`): contra cada fundo em que um alvo pode estar.
  ['accent', 'canvas'],
  ['accent', 'panel'],
  ['accent', 'sidebar'],
  ['accent', 'accent-surface'],
  ['accent-hover', 'surface'],
  ['nugget', 'surface'],
  ['nugget', 'canvas'],
]

describe('contraste dos tokens de styles.css', () => {
  it.each(TEXT_PAIRS)('texto %s sobre %s >= 4.5', (fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5)
  })

  it.each(CONTROL_PAIRS)('controle %s sobre %s >= 3', (fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(3)
  })

  it('usa accent como anel de foco e respeita prefers-reduced-motion', () => {
    const focus = /:focus-visible {([^}]*)}/.exec(css)?.[1] ?? ''
    expect(focus).toContain('outline: 3px solid var(--color-accent)')
    expect(focus).toContain('outline-offset: 3px')
    const motion = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
    expect(motion).toContain('transition-duration')
    expect(motion).toContain('animation-duration')
  })

  it('declara os tokens novos do redesenho', () => {
    for (const name of [
      'control-line',
      'accent-surface',
      'accent-ink',
      'accent-hover',
      'ink-hover',
      'subtle',
      'brand',
      'sidebar',
      'nugget',
      'nugget-ink',
      'nugget-surface',
      'scrim',
    ]) {
      expect(() => token(name)).not.toThrow()
    }
    for (const t of [
      '--radius-panel:',
      '--radius-control:',
      '--radius-chip:',
      '--text-page-title:',
      '--text-body-sm:',
      '--text-caption:',
      '--shadow-overlay:',
      '--font-display:',
    ]) {
      expect(css).toContain(t)
    }
  })

  it.each(TEXT_PAIRS)('tema escuro: texto %s sobre %s >= 4.5', (fg, bg) => {
    expect(contrastOf(darkToken(fg), darkToken(bg))).toBeGreaterThanOrEqual(4.5)
  })

  it.each(CONTROL_PAIRS)('tema escuro: controle %s sobre %s >= 3', (fg, bg) => {
    expect(contrastOf(darkToken(fg), darkToken(bg))).toBeGreaterThanOrEqual(3)
  })

  it('o bloco do sistema e o bloco data-theme escuro têm os mesmos valores', () => {
    expect(mediaDarkBlock()).toEqual(dataThemeDarkBlock())
    expect(mediaDarkText()).toContain('color-scheme: dark')
    expect(dataThemeDarkText()).toContain('color-scheme: dark')
  })

  it('usa a marca Bateia', () => {
    expect(token('accent').slice(1).toUpperCase()).toBe('1E5B4B')
    expect(token('nugget').slice(1).toUpperCase()).toBe('A87A12')
    expect(darkToken('accent').slice(1).toUpperCase()).toBe('79C2A6')
    expect(css).toContain('"Schibsted Grotesk Variable"')
    expect(css).toContain('"Young Serif"')
    expect(css).not.toContain('Inter Variable')
  })

  it('todo token --color-* do bloco claro existe nos dois blocos escuros', () => {
    const start = css.indexOf('@theme {')
    const light = Object.keys(parseColors(css.slice(start, css.indexOf('\n}', start))))
    expect(light.length).toBeGreaterThan(20)
    const missing = (block: Record<string, string>) => light.filter((name) => !(name in block))
    expect(missing(mediaDarkBlock())).toEqual([])
    expect(missing(dataThemeDarkBlock())).toEqual([])
  })

  it('info-line existe nos três blocos e tem >= 3:1 sobre info-surface', () => {
    expect(mediaDarkBlock()['info-line']).toBeDefined()
    expect(contrast('info-line', 'info-surface')).toBeGreaterThanOrEqual(3)
    expect(contrastOf(darkToken('info-line'), darkToken('info-surface'))).toBeGreaterThanOrEqual(3)
  })
})
