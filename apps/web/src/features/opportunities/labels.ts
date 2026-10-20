export const workModeLabels: Record<string, string> = {
  REMOTE: 'Remoto',
  HYBRID: 'Híbrido',
  ONSITE: 'Presencial',
  UNKNOWN: 'Não informado',
}

export const seniorityLabels: Record<string, string> = {
  INTERN: 'Estágio',
  JUNIOR: 'Júnior',
  MID: 'Pleno',
  SENIOR: 'Sênior',
  STAFF: 'Staff',
  LEAD: 'Liderança',
  MANAGER: 'Gerência',
  DIRECTOR: 'Diretoria',
  PRINCIPAL: 'Principal',
  UNKNOWN: 'Não informada',
}

export function opportunityLabel(value: string, labels: Record<string, string>): string {
  return labels[value] ?? 'Estado não reconhecido'
}
