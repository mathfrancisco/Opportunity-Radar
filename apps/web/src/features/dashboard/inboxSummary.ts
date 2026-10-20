import { daysFrom, formatHour } from '../../lib/time'
import type { InboxSummary } from './api'

/** The empty-state line. Hours are São Paulo time; wording is only invented for today and tomorrow. */
export function nothingNewSentence(summary: InboxSummary | undefined): string {
  const base = 'Nada novo desde ontem.'
  if (!summary?.nextCollectionAt) return base
  const next = new Date(summary.nextCollectionAt)
  const generated = new Date(summary.generatedAt)
  if (Number.isNaN(next.getTime()) || Number.isNaN(generated.getTime())) return base
  if (next.getTime() <= generated.getTime()) return `${base} A próxima coleta já está na fila.`
  const hour = formatHour(next)
  if (!hour) return base
  const days = daysFrom(next, generated)
  if (days === 0) return `${base} A próxima coleta roda às ${hour}.`
  if (days === 1) return `${base} A próxima coleta roda amanhã às ${hour}.`
  return base
}

/** The header sentence for the default view; null while there is no summary (the list count takes over). */
export function worthSentence(summary: InboxSummary | undefined): string | null {
  if (!summary) return null
  const { worthCount: worth, collectedCount: collected } = summary
  if (worth < 1 && collected < 1) return 'Nada novo desde ontem.'
  if (worth < 1) {
    return `Nenhuma vaga nova vale seu tempo, ${collected === 1 ? 'da 1 coletada' : `das ${collected} coletadas`} desde ontem.`
  }
  const subject = worth === 1 ? '1 vaga vale' : `${worth} vagas valem`
  const total = collected === 1 ? '1 coletada' : `${collected} coletadas`
  return `${subject} seu tempo, de ${total} desde ontem.`
}
