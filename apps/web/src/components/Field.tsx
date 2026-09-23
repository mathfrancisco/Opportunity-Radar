import { type ReactNode } from 'react'

interface FieldProps {
  label: string
  children: ReactNode
  /** Spoken to a screen reader but not drawn, for a control the layout already explains. */
  hiddenLabel?: boolean
  hint?: ReactNode
  className?: string
}

/**
 * A labelled control.
 *
 * The label wraps the control instead of pointing at it by id: a wrapped control is
 * associated even when whoever adds the next field forgets the `htmlFor`.
 */
export function Field({
  label,
  children,
  hiddenLabel = false,
  hint,
  className = '',
}: FieldProps) {
  return (
    <label className={`text-sm ${className}`.trim()}>
      <span className={hiddenLabel ? 'sr-only' : 'text-muted'}>{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

/** The shared look of every text, number and select control. */
export const controlClassName =
  'mt-1 w-full rounded-xl border border-line-strong bg-surface px-3 py-2 ' +
  'outline-none focus:border-ink focus:ring-2 focus:ring-accent'
