import { type ReactNode } from 'react'

interface ChipProps {
  children: ReactNode
  /**
   * Border, background and text classes. When given they replace the default outlined
   * look instead of being appended: two colour classes on one element are resolved by
   * stylesheet order, not by the order written.
   */
  tone?: string
  /** Shows a small dot in the text colour before the label. */
  dot?: boolean
  className?: string
}

const defaultChipTone = 'border-line-strong bg-surface text-ink'

/** Small outlined label. State is always in the text; the dot is decoration. */
export function Chip({ children, tone = defaultChipTone, dot = false, className = '' }: ChipProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-chip border px-2 py-0.5 text-caption ${tone} ${className}`.trim()}
    >
      {dot && <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}
