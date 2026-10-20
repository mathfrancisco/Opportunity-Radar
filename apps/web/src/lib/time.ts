const saoPaulo = new Intl.DateTimeFormat('pt-BR', {
  timeZone: 'America/Sao_Paulo',
  hour: 'numeric',
  minute: '2-digit',
  hourCycle: 'h23',
})

/** An hour of the day as it is said aloud in Brazil: "6h" on the hour, "14h10" otherwise. */
export function formatHour(date: Date): string {
  const parts = saoPaulo.formatToParts(date)
  const hour = Number(parts.find((part) => part.type === 'hour')?.value)
  const minute = parts.find((part) => part.type === 'minute')?.value ?? '00'
  return minute === '00' ? `${hour}h` : `${hour}h${minute}`
}
