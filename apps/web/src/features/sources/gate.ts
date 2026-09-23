import { type SourceDefinition } from './api'

export interface ControlsDraft {
  termsReviewed: boolean
  collectorLocalTested: boolean
  /** yyyy-mm-dd from the date input; empty keeps the review date already recorded. */
  reviewedOn: string
}

export function draftFrom(source: SourceDefinition): ControlsDraft {
  return {
    termsReviewed: source.termsReviewed,
    collectorLocalTested: source.collectorLocalTested,
    reviewedOn: source.reviewedAt ? source.reviewedAt.slice(0, 10) : '',
  }
}

/**
 * What still stands between this source and running, read from the record itself.
 *
 * The screen does not decide the gate — the server does, and refuses again if this list
 * is wrong. It exists so the operator learns what is missing before sending, instead of
 * after. A manual source has no gate: the domain already treats it as the exception.
 */
export function missingForEnable(source: SourceDefinition, draft: ControlsDraft): string[] {
  if (source.sourceType === 'manual') return []
  const missing: string[] = []
  if (source.evidenceStatus !== 'confirmed') {
    missing.push(
      `evidência confirmada — hoje é “${source.evidenceStatus}”. A evidência só é confirmada pelo teste do collector contra o endpoint público, que não roda pela interface.`,
    )
  }
  if (!draft.reviewedOn && !source.reviewedAt) missing.push('data de revisão')
  if (!draft.termsReviewed) missing.push('termos revisados')
  if (!draft.collectorLocalTested) missing.push('collector testado localmente')
  return missing
}
