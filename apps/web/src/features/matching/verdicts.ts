/**
 * The deterministic verdict, named once.
 *
 * Two label maps on purpose: the Inbox labels one opportunity and the Overview labels a
 * count of them. The tone, which carries the meaning, is single.
 */

export const verdictLabels: Record<string, string> = {
  HIGH_PRIORITY: 'Alta prioridade',
  RECOMMENDED: 'Recomendada',
  WATCHLIST: 'Observação',
  REVIEW_REQUIRED: 'Revisão necessária',
  LOW_MATCH: 'Baixa aderência',
  INELIGIBLE: 'Inelegível',
}

export const verdictCountLabels: Record<string, string> = {
  HIGH_PRIORITY: 'Alta prioridade',
  RECOMMENDED: 'Recomendadas',
  WATCHLIST: 'Observação',
  REVIEW_REQUIRED: 'Revisão necessária',
  LOW_MATCH: 'Baixa aderência',
  INELIGIBLE: 'Inelegíveis',
}

export const verdictTones: Record<string, string> = {
  HIGH_PRIORITY: 'border-success-line bg-success-surface text-success-ink',
  RECOMMENDED: 'border-success-line bg-success-surface-soft text-success-ink',
  REVIEW_REQUIRED: 'border-warning-line bg-warning-surface text-warning-ink',
  WATCHLIST: 'border-line-strong bg-canvas text-neutral-ink',
  LOW_MATCH: 'border-line-strong bg-canvas text-muted',
  INELIGIBLE: 'border-danger-line bg-danger-surface text-danger-ink',
}

/** Display order of the verdicts, strongest first. */
export const verdictOrder = [
  'HIGH_PRIORITY',
  'RECOMMENDED',
  'REVIEW_REQUIRED',
  'WATCHLIST',
  'LOW_MATCH',
  'INELIGIBLE',
] as const
