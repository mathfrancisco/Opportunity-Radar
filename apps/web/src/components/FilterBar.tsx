import { type ReactNode } from 'react'

interface FilterBarProps {
  /** The `FilterPill`s, in reading order. */
  children: ReactNode
  /** Usually a `SearchInput`; goes to the right and takes its own full-width line below `md`. */
  search?: ReactNode
  /** Labels the group of filters for assistive tech. */
  label?: string
  className?: string
}

/**
 * The filter row: pills on the left, search on the right.
 *
 * It wraps instead of overflowing (SPEC 46, 10): on a narrow screen the pills break onto
 * further lines and the search gets a line of its own, full width. The "Buscas salvas"
 * dropdown (D12) is not here yet; F46-07 decides where it docks.
 */
export function FilterBar({ children, search, label = 'Filtros', className = '' }: FilterBarProps) {
  return (
    <div className={`mt-5 flex flex-wrap items-center gap-2 ${className}`.trim()}>
      <div aria-label={label} className="flex min-w-0 flex-wrap items-center gap-2" role="group">
        {children}
      </div>
      {search && <div className="w-full md:ml-auto md:w-auto">{search}</div>}
    </div>
  )
}
