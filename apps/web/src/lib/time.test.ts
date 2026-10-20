import { describe, expect, it } from 'vitest'
import { formatHour } from './time'

describe('formatHour', () => {
  it('writes a whole hour without minutes, in São Paulo time', () => {
    expect(formatHour(new Date('2026-10-20T09:00:00Z'))).toBe('6h')
  })

  it('writes minutes with two digits', () => {
    expect(formatHour(new Date('2026-10-20T17:10:00Z'))).toBe('14h10')
    expect(formatHour(new Date('2026-10-20T17:05:00Z'))).toBe('14h05')
  })

  it('does not pad the hour and reads midnight as 0h', () => {
    expect(formatHour(new Date('2026-10-20T03:00:00Z'))).toBe('0h')
  })
})
