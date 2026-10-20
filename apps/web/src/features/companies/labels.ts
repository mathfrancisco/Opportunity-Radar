/**
 * Company vocabulary in pt-BR, named once for the list and the detail.
 *
 * An unmapped code reads "Em revisão" and never the code itself (DESIGN.md §8): the raw
 * value belongs in a "Detalhe técnico", not in the main text.
 */

export const priorityLabels: Record<string, string> = {
  high: 'Alta',
  normal: 'Normal',
  low: 'Baixa',
}

export const companyStatusLabels: Record<string, string> = {
  active: 'Ativa',
  paused: 'Pausada',
  backlog: 'Em fila',
}

export const verificationLabels: Record<string, string> = {
  api_json_confirmed: 'API JSON confirmada',
  VERIFIED: 'Verificada',
  PENDING: 'Pendente',
  UNVERIFIED: 'Não verificada',
  unknown: 'Não informada',
  unverified: 'Não verificada',
  ats_identified: 'ATS identificado',
  careers_confirmed: 'Carreiras confirmadas',
  research_recorded: 'Pesquisa registrada',
  backlog: 'Em fila de homologação',
}

export function companyLabel(value: string, labels: Record<string, string>): string {
  return labels[value] ?? 'Em revisão'
}
