const saoPaulo = new Intl.DateTimeFormat('pt-BR', {
  timeZone: 'America/Sao_Paulo',
  hour: 'numeric',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** An hour of the day as it is said aloud in Brazil: "6h" on the hour, "14h10" otherwise. */
export function formatHour(date: Date): string {
  if (Number.isNaN(date.getTime())) return ''
  const parts = saoPaulo.formatToParts(date)
  const hour = Number(parts.find((part) => part.type === 'hour')?.value)
  const minute = parts.find((part) => part.type === 'minute')?.value ?? '00'
  return minute === '00' ? `${hour}h` : `${hour}h${minute}`
}

const saoPauloDay = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Sao_Paulo',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
})

function dayNumber(date: Date): number {
  const parts = saoPauloDay.formatToParts(date)
  const part = (type: string) => Number(parts.find((entry) => entry.type === type)?.value)
  return Date.UTC(part('year'), part('month') - 1, part('day')) / 86_400_000
}

/** Whole São Paulo calendar days from `from` to `date` (0 same day, 1 next day); NaN if invalid. */
export function daysFrom(date: Date, from: Date): number {
  if (Number.isNaN(date.getTime()) || Number.isNaN(from.getTime())) return Number.NaN
  return dayNumber(date) - dayNumber(from)
}
