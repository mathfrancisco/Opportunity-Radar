/** How a source's evidence and a run's trigger read to a person. Unknown values never show their code. */
export const evidenceLabels: Record<string, string> = {
  unverified: 'não verificada',
  ats_identified: 'sistema identificado',
  confirmed: 'confirmada',
}

export const triggerLabels: Record<string, string> = {
  ON_DEMAND: 'Manual',
  SCHEDULED: 'Agendada',
}

/** What the last run says in plain words; null when there is nothing to report. */
export function sourceRunSentence(name: string, status: string | null): string | null {
  if (status === 'FAILED') return `A última coleta em ${name} não terminou.`
  if (status === 'PARTIAL') return `A última coleta em ${name} trouxe só parte das vagas.`
  return null
}
