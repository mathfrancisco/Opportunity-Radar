import type { MatchFactor } from './api'

/** Inbox score (0-100, as text) to the number of filled nuggets out of 10; null when there is no score. */
export function nuggetsFromScore(score: string | null): number | null {
  if (score === null) return null
  const value = Number(score)
  if (!Number.isFinite(value)) return null
  return Math.round(Math.min(100, Math.max(0, value)) / 10)
}

/** One nugget per applicable factor: met, missed (known but weak) or unknown. */
export function countFactors(factors: MatchFactor[]): { met: number; missed: number; unknown: number } {
  const counts = { met: 0, missed: 0, unknown: 0 }
  for (const factor of factors) {
    if (factor.status === 'KNOWN') {
      if (factor.rawScore !== null && Number(factor.rawScore) >= 0.5) counts.met += 1
      else counts.missed += 1
    } else if (factor.status === 'UNKNOWN') {
      counts.unknown += 1
    }
  }
  return counts
}
