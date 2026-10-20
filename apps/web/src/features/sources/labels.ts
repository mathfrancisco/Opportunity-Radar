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
