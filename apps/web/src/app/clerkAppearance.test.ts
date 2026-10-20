import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { clerkAppearance } from './clerkAppearance'

const css = readFileSync(join(__dirname, '..', 'styles.css'), 'utf8')
const variables = (clerkAppearance.variables ?? {}) as Record<string, unknown>

describe('clerkAppearance', () => {
  it('themes Clerk only through existing Bateia tokens', () => {
    const entries = Object.entries(variables)
    expect(entries.length).toBeGreaterThan(0)
    for (const [key, value] of entries) {
      expect(value, key).toMatch(/^var\(--(color|font|radius)-[a-z0-9-]+\)$/)
      const token = String(value).slice(4, -1)
      expect(css.includes(`  ${token}:`), `${key} -> ${token}`).toBe(true)
    }
  })

  it('has no hex literal', () => {
    expect(JSON.stringify(clerkAppearance)).not.toMatch(/#[0-9a-f]{3,8}\b/i)
  })

  it('sets the keys the sign-in card relies on', () => {
    for (const key of ['colorPrimary', 'colorBackground', 'colorForeground', 'colorInput', 'colorDanger', 'borderRadius', 'fontFamily']) {
      expect(variables[key], key).toBeDefined()
    }
  })
})
