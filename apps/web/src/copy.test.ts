import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = join(__dirname)
const dirs = ['routes', 'components', 'features']
const banned = [
  'Opportunity Radar',
  'Análise semântica',
  'Fatores do score',
  'Filtros eliminatórios',
  'Procedência',
  'decisão determinística',
]

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return walk(path)
    return path.endsWith('.tsx') && !path.endsWith('.test.tsx') ? [path] : []
  })
}

function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split('\n')
    .filter((line) => !line.trim().startsWith('//'))
    .join('\n')
}

describe('Bateia voice guard', () => {
  it('keeps retired terms out of rendered source', () => {
    const hits: string[] = []
    for (const dir of dirs) {
      for (const file of walk(join(root, dir))) {
        const text = stripComments(readFileSync(file, 'utf8'))
        for (const term of banned) {
          if (text.includes(term)) hits.push(`${relative(root, file)}: ${term}`)
        }
      }
    }
    expect(hits).toEqual([])
  })
})
