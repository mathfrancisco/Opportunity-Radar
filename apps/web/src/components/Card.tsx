import { type ElementType, type ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  /** `article` for a list entry, `li` inside a list, `div` for a plain panel. */
  as?: ElementType
  /** Adds the hover affordance used by cards that are themselves a link target. */
  interactive?: boolean
  className?: string
}

export function Card({
  children,
  as: Component = 'div',
  interactive = false,
  className = '',
}: CardProps) {
  const hover = interactive ? ' transition hover:border-ink' : ''
  return (
    <Component className={`rounded-2xl border border-line bg-surface p-5${hover} ${className}`.trim()}>
      {children}
    </Component>
  )
}
