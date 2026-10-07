import { type ReactNode } from 'react'

interface FilterBarProps {
  /** The `FilterPill`s, in reading order. */
  children: ReactNode
  /** Usually a `SearchInput`; goes to the right and takes its own full-width line below `md`. */
  search?: ReactNode
  /** Labels the group of filters for assistive tech. */
  label?: string
  /**
   * `toolbar` (SPEC 54): one row bounded by rules above and below, search first, then the
   * filters, so the controls read as part of the list they change. Default keeps the old row.
   */
  variant?: 'default' | 'toolbar'
  className?: string
}

/**
 * The filter row: pills on the left, search on the right.
 *
 * It wraps instead of overflowing (SPEC 46, 10): on a narrow screen the pills break onto
 * further lines and the search gets a line of its own, full width. The "Buscas salvas"
 * dropdown (D12) is not here yet; F46-07 decides where it docks.
 */
export function FilterBar({
  children,
  search,
  label = 'Filtros',
  variant = 'default',
  className = '',
}: FilterBarProps) {
  const group = (
    <div aria-label={label} className="flex min-w-0 flex-wrap items-center gap-2" role="group">
      {children}
    </div>
  )
  if (variant === 'toolbar') {
    return (
      <div
        className={`flex flex-wrap items-center gap-3 border-y border-line py-4 ${className}`.trim()}
      >
        {search && <div className="w-full md:min-w-64 md:max-w-md md:flex-1">{search}</div>}
        {group}
      </div>
    )
  }
  return (
    <div className={`mt-5 flex flex-wrap items-center gap-2 ${className}`.trim()}>
      {group}
      {search && <div className="w-full md:ml-auto md:w-auto">{search}</div>}
    </div>
  )
}
