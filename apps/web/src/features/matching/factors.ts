/** Plain-language names of the matching factors, shared by the Inbox and the detail. */
export const factorLabels: Record<string, string> = {
  GEOGRAPHY_CONTRACT_FIT: 'Local e contrato',
  TECHNOLOGY_FIT: 'Skills da vaga',
  COMPANY_PRIORITY: 'Prioridade da empresa',
  DOMAIN_EXPERIENCE: 'Experiência na área',
  SENIORITY_SCOPE: 'Nível e escopo',
  CONTRACT_COMPENSATION: 'Contrato e salário',
  TIMEZONE: 'Fuso horário',
  RECENCY: 'Vaga recente',
}

/** "Skills da vaga" -> "Combina em skills da vaga."; null for an unknown code, never the raw code. */
export function topFactorSentence(code: string | null): string | null {
  const label = code ? factorLabels[code] : undefined
  if (!label) return null
  return `Combina em ${label.charAt(0).toLowerCase()}${label.slice(1)}.`
}
