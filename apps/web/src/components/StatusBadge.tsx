import { type ReactNode } from 'react'

export interface StatusBadgeProps {
  /** The persisted state. `null` means the thing never reached a state at all. */
  value: string | null
  labels: Record<string, string>
  tones: Record<string, string>
  /** What to show for `null`; a state that never happened is not an unknown state. */
  absent?: ReactNode
}

const neutralTone = 'border-line-strong bg-canvas text-neutral-ink'

/**
 * A state, rendered the same way everywhere.
 *
 * The badge knows nothing about sources, runs or verdicts: it is handed the maps. A state
 * without a label shows its own code rather than a friendly word — inventing "desconhecido"
 * for a value the backend named would hide exactly the case worth reading.
 */
export function StatusBadge({ value, labels, tones, absent }: StatusBadgeProps) {
  if (value === null) {
    return (
      <span className="inline-flex rounded-full border border-dashed border-line-strong px-3 py-1 text-xs text-muted">
        {absent ?? 'Sem registro'}
      </span>
    )
  }
  return (
    <span
      className={`inline-flex rounded-full border px-3 py-1 text-xs font-medium ${
        tones[value] ?? neutralTone
      }`}
    >
      {labels[value] ?? value}
    </span>
  )
}
