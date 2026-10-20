import { type ReactNode } from 'react'
import { Chip } from './Chip'

export interface StatusBadgeProps {
  /** The persisted state. `null` means the thing never reached a state at all. */
  value: string | null
  labels: Record<string, string>
  tones: Record<string, string>
  /** What to show for `null`; a state that never happened is not an unknown state. */
  absent?: ReactNode
}

const neutralTone = 'border-line-strong bg-canvas text-neutral-ink'
const absentTone = 'border-dashed border-line-strong bg-surface text-muted'

/**
 * A state, rendered the same way everywhere, as an outlined `Chip`.
 *
 * The badge knows nothing about sources, runs or verdicts: it is handed the maps. A state
 * without a label reads "Estado não reconhecido"; the raw code is a technical detail and
 * never main text (DESIGN.md §8).
 */
export function StatusBadge({ value, labels, tones, absent }: StatusBadgeProps) {
  if (value === null) {
    return <Chip tone={absentTone}>{absent ?? 'Sem registro'}</Chip>
  }
  return <Chip tone={tones[value] ?? neutralTone}>{labels[value] ?? 'Estado não reconhecido'}</Chip>
}
