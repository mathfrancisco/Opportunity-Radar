import { type ReactNode } from 'react'

interface DataTableProps {
  /** Column headings, in order. */
  columns: ReactNode[]
  children: ReactNode
  /** Describes the table to a screen reader when the heading above it is not enough. */
  caption?: string
  className?: string
}

/**
 * A dense table that scrolls inside its own container.
 *
 * The container is what keeps a six-column table from pushing the whole page sideways,
 * which is how the first column — the one naming the row — goes off screen first.
 */
export function DataTable({ columns, children, caption, className = '' }: DataTableProps) {
  return (
    <div className={`overflow-x-auto ${className}`.trim()}>
      <table className="w-full border-collapse text-left text-sm">
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
