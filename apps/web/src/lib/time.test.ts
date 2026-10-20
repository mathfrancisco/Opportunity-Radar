import { describe, expect, it } from 'vitest'
import { daysFrom, formatHour } from './time'

describe('formatHour', () => {
  it('writes a whole hour without minutes, in São Paulo time', () => {
    expect(formatHour(new Date('2026-10-20T09:00:00Z'))).toBe('6h')
  })

  it('writes minutes with two digits', () => {
    expect(formatHour(new Date('2026-10-20T17:10:00Z'))).toBe('14h10')
    expect(formatHour(new Date('2026-10-20T17:05:00Z'))).toBe('14h05')
  })

  it('returns an empty string for an invalid date', () => {
    expect(formatHour(new Date('not a date'))).toBe('')
  })

  it('does not pad the hour and reads midnight as 0h', () => {
    expect(formatHour(new Date('2026-10-20T03:00:00Z'))).toBe('0h')
  })
})

describe('daysFrom', () => {
  it('counts São Paulo calendar days, not 24-hour spans', () => {
    const from = new Date('2026-10-20T23:00:00Z')
    expect(daysFrom(new Date('2026-10-20T14:00:00Z'), from)).toBe(0)
    expect(daysFrom(new Date('2026-10-21T02:30:00Z'), from)).toBe(0)
    expect(daysFrom(new Date('2026-10-21T09:00:00Z'), from)).toBe(1)
    expect(daysFrom(new Date('2026-10-23T09:00:00Z'), from)).toBe(3)
  })

  it('is NaN for an invalid date', () => {
    expect(daysFrom(new Date('x'), new Date())).toBeNaN()
  })
})
