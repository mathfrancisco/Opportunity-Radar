import { type ElementType, type ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  /** `article` for a list entry, `li` inside a list, `div` for a plain panel. */
  as?: ElementType
  /** Adds the hover affordance used by cards that are themselves a link target. */
  interactive?: boolean
  /** No frame, background or padding: for content that already sits in a framed panel. */
  bare?: boolean
  className?: string
}

export function Card({
  children,
  as: Component = 'div',
  interactive = false,
  bare = false,
  className = '',
}: CardProps) {
  const hover = interactive ? ' transition hover:border-ink' : ''
  const frame = bare ? '' : 'rounded-control border border-line bg-surface p-5'
  return (
    <Component className={`${frame}${hover} ${className}`.trim()}>
      {children}
    </Component>
  )
}
