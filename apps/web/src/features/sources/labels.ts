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

/** How a collector reads to a person. Unknown types never show their slug. */
export const sourceTypeLabels: Record<string, string> = {
  ashby: 'Ashby',
  lever: 'Lever',
  greenhouse: 'Greenhouse',
  workday: 'Workday',
  workable: 'Workable',
  remotive: 'Remotive',
  teamtailor: 'Teamtailor',
  factorial: 'Factorial',
  inhire: 'inHire',
  jobposting: 'Página de vaga (JobPosting)',
  hacker_news: 'Hacker News',
  tavily_search: 'Busca na web (Tavily)',
  manual: 'Manual (entrada avulsa de vaga)',
}

export function sourceTypeLabel(sourceType: string): string {
  return sourceTypeLabels[sourceType] ?? 'Tipo não reconhecido'
}
