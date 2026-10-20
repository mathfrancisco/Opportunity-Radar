import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = join(__dirname)
const dirs = ['app', 'routes', 'components', 'features']
const banned = [
  'Opportunity Radar',
  'Análise semântica',
  'Fatores do score',
  'Filtros eliminatórios',
  'Procedência',
  'decisão determinística',
]

// Product word is "vaga" (DESIGN.md §8). Add { file, text } here only with a justification.
const oportunidadeAllowlist: { file: string; text: string }[] = []
const oportunidade = /\boportunidades?\b/i

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return walk(path)
    return /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path) ? [path] : []
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
          if (text.toLowerCase().includes(term.toLowerCase())) hits.push(`${relative(root, file)}: ${term}`)
        }
        const name = relative(root, file).replaceAll('\\', '/')
        for (const line of text.split('\n')) {
          if (!oportunidade.test(line)) continue
          if (oportunidadeAllowlist.some((a) => a.file === name && line.includes(a.text))) continue
          hits.push(`${name}: oportunidade -> ${line.trim().slice(0, 100)}`)
        }
      }
    }
    expect(hits).toEqual([])
  })
})
