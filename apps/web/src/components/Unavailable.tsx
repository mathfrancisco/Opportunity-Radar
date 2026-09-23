interface UnavailableProps {
  /** Why the value is missing, spoken to a screen reader and shown on hover. */
  reason?: string
}

/**
 * A value the system does not have.
 *
 * Never `0` and never an empty cell: a rate with no run behind it and a rate of zero are
 * different facts, and the phase 13 metrics exist precisely to keep them apart. The dash is
 * for the eye; the reason is for everyone else.
 */
export function Unavailable({ reason = 'sem dados' }: UnavailableProps) {
  return (
    <span className="text-muted" title={reason}>
      <span aria-hidden="true">—</span>
      <span className="sr-only">{reason}</span>
    </span>
  )
}
