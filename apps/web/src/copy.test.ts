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

/**
 * Drops block comments and whole-line // comments. A line that starts with // is kept when it is
 * rendered text: inside a template literal (odd backtick count so far) or right after a JSX tag.
 */
function stripComments(source: string): string {
  const out: string[] = []
  let backticks = 0
  let previous = ''
  for (const line of source.replace(/\/\*[\s\S]*?\*\//g, '').split('\n')) {
    const wholeLineComment = /^\s*\/\//.test(line) && backticks % 2 === 0 && !previous.endsWith('>')
    if (!wholeLineComment) {
      out.push(line)
      backticks += (line.match(/`/g) ?? []).length
      if (line.trim()) previous = line.trim()
    }
  }
  return out.join('\n')
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

  it('keeps labels in sentence case (no uppercase with wide tracking)', () => {
    const hits: string[] = []
    for (const dir of dirs) {
      for (const file of walk(join(root, dir))) {
        const text = stripComments(readFileSync(file, 'utf8'))
        if (/\buppercase\b[^"'`]*\btracking-\[|\btracking-\[[^"'`]*\buppercase\b/.test(text)) {
          hits.push(relative(root, file))
        }
      }
    }
    expect(hits).toEqual([])
  })

  it('does not call the reading "análise por IA"', () => {
    const hits: string[] = []
    for (const dir of dirs) {
      for (const file of walk(join(root, dir))) {
        if (/análise por IA/i.test(stripComments(readFileSync(file, 'utf8')))) hits.push(relative(root, file))
      }
    }
    expect(hits).toEqual([])
  })

  it('strips only whole-line // comments, not rendered text', () => {
    expect(stripComments('  // análise por IA\nconst a = 1')).not.toContain('análise')
    expect(stripComments('<p>\n//análise por IA\n</p>')).toContain('análise')
    expect(stripComments('const t = `\n// análise por IA\n`')).toContain('análise')
    expect(stripComments("const u = 'http://x'")).toContain('http')
    expect(stripComments('const a = 1 // note')).toContain('note')
  })
})
