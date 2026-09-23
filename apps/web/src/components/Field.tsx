import { type ReactElement, type ReactNode, cloneElement, useId } from 'react'

interface FieldProps {
  label: string
  children: ReactNode
  /** Spoken to a screen reader but not drawn, for a control the layout already explains. */
  hiddenLabel?: boolean
  hint?: ReactNode
  /** What the server or the form refused, shown under the control and read with it. */
  error?: ReactNode
  className?: string
}

/**
 * A labelled control.
 *
 * The label wraps the control instead of pointing at it by id: a wrapped control is
 * associated even when whoever adds the next field forgets the `htmlFor`.
 *
 * An error is not only red text below the field. It is announced with the field, through
 * `aria-invalid` and `aria-describedby`, because a screen reader lands on the input and
 * never on the paragraph after it.
 */
export function Field({
  label,
  children,
  hiddenLabel = false,
  hint,
  error,
  className = '',
}: FieldProps) {
  const errorId = useId()
  const labelId = useId()
  const hintId = useId()
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ')
  // Named by the label text alone. Wrapping is kept for the association, but a wrapped
  // select would otherwise lend its chosen option to the name: "Tipo Greenhouse".
  const described = isControl(children)
    ? cloneElement(children, {
        'aria-labelledby': labelId,
        ...(describedBy ? { 'aria-describedby': describedBy } : {}),
        ...(error ? { 'aria-invalid': true } : {}),
      })
    : children
  return (
    <label className={`text-sm ${className}`.trim()}>
      <span className={hiddenLabel ? 'sr-only' : 'text-muted'} id={labelId}>
        {label}
      </span>
      {described}
      {hint && (
        <span className="mt-1 block text-xs text-muted" id={hintId}>
          {hint}
        </span>
      )}
      {error && (
        <span className="mt-1 block text-xs text-danger-ink" id={errorId}>
          {error}
        </span>
      )}
    </label>
  )
}

function isControl(children: ReactNode): children is ReactElement<Record<string, unknown>> {
  return (
    typeof children === 'object' &&
    children !== null &&
    'type' in children &&
    typeof (children as ReactElement).type === 'string'
  )
}

/** The shared look of every text, number and select control. */
export const controlClassName =
  'mt-1 w-full rounded-xl border border-line-strong bg-surface px-3 py-2 ' +
  'outline-none focus:border-ink focus:ring-2 focus:ring-accent ' +
  'aria-invalid:border-danger-ink aria-invalid:ring-danger-line'
