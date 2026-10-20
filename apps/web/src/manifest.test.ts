import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { inflateSync } from 'node:zlib'
import { describe, expect, it } from 'vitest'

const publicDir = resolve(process.cwd(), 'public')

function decodePng(file: string) {
  const buf = readFileSync(resolve(publicDir, file))
  expect(buf.subarray(1, 4).toString('latin1')).toBe('PNG')
  let pos = 8
  let width = 0
  let height = 0
  let colorType = 0
  const idat: Buffer[] = []
  while (pos < buf.length) {
    const len = buf.readUInt32BE(pos)
    const type = buf.subarray(pos + 4, pos + 8).toString('latin1')
    const data = buf.subarray(pos + 8, pos + 8 + len)
    if (type === 'IHDR') {
      width = data.readUInt32BE(0)
      height = data.readUInt32BE(4)
      expect(data[8]).toBe(8)
      colorType = data[9]
    }
    if (type === 'IDAT') idat.push(data)
    pos += 12 + len
  }
  const channels = colorType === 6 ? 4 : colorType === 2 ? 3 : 0
  expect(channels).toBeGreaterThan(0)
  const raw = inflateSync(Buffer.concat(idat))
  // First scanline: filter byte, then pixel 0 (filter is irrelevant for the first pixel except Sub/Up/Avg/Paeth, which all reduce to raw for x=0,y=0).
  const pixel = [...raw.subarray(1, 1 + channels)]
  return { width, height, alpha: channels === 4 ? pixel[3] : 255 }
}

describe('manifest e ícones', () => {
  const manifest = JSON.parse(readFileSync(resolve(publicDir, 'site.webmanifest'), 'utf8')) as {
    icons: { src: string; sizes: string; purpose?: string }[]
  }

  it('declara ícone maskable 512x512 que existe', () => {
    const icon = manifest.icons.find((i) => i.purpose === 'maskable')
    expect(icon).toMatchObject({ src: '/icon-maskable-512.png', sizes: '512x512' })
    expect(existsSync(resolve(publicDir, 'icon-maskable-512.png'))).toBe(true)
    const png = decodePng('icon-maskable-512.png')
    expect([png.width, png.height]).toEqual([512, 512])
    expect(png.alpha).toBe(255)
  })

  it('apple-touch-icon é 180x180 e o pixel (0,0) é opaco', () => {
    const png = decodePng('apple-touch-icon.png')
    expect([png.width, png.height]).toEqual([180, 180])
    expect(png.alpha).toBe(255)
  })
})
