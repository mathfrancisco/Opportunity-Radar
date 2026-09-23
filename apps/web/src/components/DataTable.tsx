import { type ReactNode } from 'react'

interface DataTableProps {
  /** Column headings, in order. */
  columns: ReactNode[]
  children: ReactNode
  /** Describes the table to a screen reader when the heading above it is not enough. */
  caption?: string
  /**
   * Pins the first column while the rest scrolls. Worth it when that column is what names
   * the row — scrolling a metrics table sideways and losing the source name leaves six
   * numbers belonging to nobody.
   */
  stickyFirstColumn?: boolean
  /** Lets a disclosure button point at this table with `aria-controls`. */
  id?: string
  className?: string
}

/**
 * A dense table that scrolls inside its own container.
 *
 * The container is what keeps a six-column table from pushing the whole page sideways,
 * which is how the first column goes off screen first and the page starts scrolling in two
 * directions at once.
 */
export function DataTable({
  columns,
  children,
  caption,
  stickyFirstColumn = false,
  id,
  className = '',
}: DataTableProps) {
  const sticky = stickyFirstColumn
    ? ' [&_td:first-child]:sticky [&_td:first-child]:left-0 [&_td:first-child]:bg-surface' +
      ' [&_th:first-child]:sticky [&_th:first-child]:left-0 [&_th:first-child]:bg-canvas'
    : ''
  return (
    <div className={`overflow-x-auto ${className}`.trim()} id={id}>
      <table className={`w-full border-collapse text-left text-sm${sticky}`}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-canvas text-xs uppercase tracking-[0.08em] text-muted">
          <tr>
            {columns.map((column, index) => (
              <th className="px-4 py-3 font-semibold" key={index} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}
