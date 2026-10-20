import { describe, expect, it } from 'vitest'
import type { MatchFactor } from './api'
import { countFactors, factorState, nuggetsFromScore } from './nuggets'

function factor(status: string, rawScore: string | null): MatchFactor {
  return {
    factorCode: 'F',
    weight: '1',
    rawScore,
    contribution: '0',
    status,
    confidence: '1',
    missingPolicy: 'NEUTRAL',
    explanation: '',
    evidenceRefs: [],
  }
}

describe('nuggets', () => {
  it('converte o score 0-100 em pepitas', () => {
    expect(nuggetsFromScore('76.0')).toBe(8)
    expect(nuggetsFromScore('4.9')).toBe(0)
    expect(nuggetsFromScore('130')).toBe(10)
    expect(nuggetsFromScore(null)).toBeNull()
    expect(nuggetsFromScore('n/d')).toBeNull()
  })

  it('conta fatores atendidos, faltantes e sem dado', () => {
    expect(
      countFactors([
        factor('KNOWN', '0.9'),
        factor('KNOWN', '0.2'),
        factor('KNOWN', null),
        factor('UNKNOWN', null),
        factor('NOT_APPLICABLE', null),
      ]),
    ).toEqual({ met: 1, missed: 2, unknown: 1 })
    expect(countFactors([factor('NOT_APPLICABLE', null)])).toEqual({ met: 0, missed: 0, unknown: 0 })
  })

  it('classifica cada fator', () => {
    expect(factorState(factor('KNOWN', '0.5'))).toBe('met')
    expect(factorState(factor('KNOWN', '0.49'))).toBe('missed')
    expect(factorState(factor('KNOWN', null))).toBe('missed')
    expect(factorState(factor('UNKNOWN', null))).toBe('unknown')
    expect(factorState(factor('NOT_APPLICABLE', null))).toBeNull()
  })
})
