import { type ReactNode } from 'react'

/*
 * Peças finas para o interior de uma célula de `DataTable` (SPEC 46, 5): texto primário
 * em destaque com o secundário cinza embaixo, data escura com hora cinza, avatar de
 * iniciais. Não sabem de domínio: recebem o texto pronto.
 */

/** The bold, dark line that names the row. */
export function PrimaryText({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return <span className={`block font-semibold text-ink ${className}`.trim()}>{children}</span>
}

/** The grey line under (or beside) the primary text. `muted` passes 4.5:1 on `surface`. */
export function SecondaryText({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return <span className={`block text-caption text-muted ${className}`.trim()}>{children}</span>
}

interface DateTimeCellProps {
  /** ISO 8601 instant. */
  value: string | Date
  /** IANA zone; defaults to the browser's. Fixed in tests so they do not depend on the machine. */
  timeZone?: string
  /** Shown when `value` is not a date. */
  fallback?: ReactNode
}

/** Date in `ink`, time in `muted`, one above the other; `<time>` carries the machine value. */
export function DateTimeCell({ value, timeZone, fallback = '—' }: DateTimeCellProps) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return <span className="text-muted">{fallback}</span>
  const day = date.toLocaleDateString('pt-BR', { timeZone })
  const time = date.toLocaleTimeString('pt-BR', { timeZone, hour: '2-digit', minute: '2-digit' })
  return (
    <time dateTime={date.toISOString()}>
      <span className="block text-ink">{day}</span>
      <span className="block text-caption text-muted">{time}</span>
    </time>
  )
}

/** First letter of the first and of the last word: "Ana Maria Souza" is "AS". */
function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '?'
  const first = words[0][0]
  const last = words.length > 1 ? words[words.length - 1][0] : ''
  return `${first}${last}`.toUpperCase()
}

/**
 * A circle with initials. No image: there is no author in the radar yet. Decorative, since
 * the name always sits beside it and reading it twice helps nobody.
 */
export function Avatar({ name, className = '' }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-line-strong bg-panel text-caption font-semibold text-subtle ${className}`.trim()}
    >
      {initialsOf(name)}
    </span>
  )
}
