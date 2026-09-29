import { type ReactNode, useEffect, useRef } from 'react'

interface DataTableProps {
  /** Column headings, in order. With `selectable`, the selection column comes before them. */
  columns: ReactNode[]
  children: ReactNode
  /** Describes the table to a screen reader when the heading above it is not enough. */
  caption?: string
  /**
   * Pins the first column while the rest scrolls. Worth it when that column is what names
   * the row — scrolling a metrics table sideways and losing the source name leaves six
   * numbers belonging to nobody. With `selectable` the first column is the checkbox.
   */
  stickyFirstColumn?: boolean
  /**
   * Adds a leading column with the "select all" checkbox. Opt-in: no screen has a bulk
   * action yet. The table only draws the header checkbox; rows render their own `RowSelect`
   * and the caller owns the selection.
   */
  selectable?: boolean
  allSelected?: boolean
  someSelected?: boolean
  onToggleAll?: (selected: boolean) => void
  /** Visible to assistive tech only; the header cell has no room for text. */
  selectAllLabel?: string
  /** Lets a disclosure button point at this table with `aria-controls`. */
  id?: string
  className?: string
}

const checkboxClass = 'h-4 w-4 rounded-chip border border-control-line accent-ink'

/** The checkbox of one row. Needs a label that names the row: "selecionar" alone says nothing. */
export function RowSelect({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (selected: boolean) => void
}) {
  return (
    <input
      aria-label={label}
      checked={checked}
      className={checkboxClass}
      onChange={(event) => onChange(event.target.checked)}
      type="checkbox"
    />
  )
}

/**
 * A dense table that scrolls inside its own bordered container.
 *
 * The container is what keeps a six-column table from pushing the whole page sideways,
 * which is how the first column goes off screen first and the page starts scrolling in two
 * directions at once. Rows are at least 44px tall (SPEC 46, 4.3); a `td` height is the
 * table's way of saying "minimum", which `min-height` on a `tr` is not.
 */
export function DataTable({
  columns,
  children,
  caption,
  stickyFirstColumn = false,
  selectable = false,
  allSelected = false,
  someSelected = false,
  onToggleAll,
  selectAllLabel = 'Selecionar todas',
  id,
  className = '',
}: DataTableProps) {
  const selectAll = useRef<HTMLInputElement>(null)
  useEffect(() => {
    // `indeterminate` exists only as a DOM property, never as an attribute.
    if (selectAll.current) selectAll.current.indeterminate = someSelected && !allSelected
  }, [someSelected, allSelected])

  const sticky = stickyFirstColumn
    ? ' [&_td:first-child]:sticky [&_td:first-child]:left-0 [&_td:first-child]:bg-surface' +
      ' [&_th:first-child]:sticky [&_th:first-child]:left-0 [&_th:first-child]:bg-panel'
    : ''
  return (
    <div
      className={`relative overflow-x-auto rounded-control border border-line bg-surface ${className}`.trim()}
      id={id}
    >
      <table
        className={
          'w-full border-collapse text-left text-body-sm [&_tbody_td]:h-11 [&_tbody_td]:px-4 ' +
          `[&_tbody_td]:py-2 [&_tbody_tr]:border-t [&_tbody_tr]:border-line${sticky}`
        }
      >
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="bg-panel text-caption text-muted">
          <tr>
            {selectable && (
              <th className="w-10 px-4 py-2.5" scope="col">
                <input
                  aria-label={selectAllLabel}
                  checked={allSelected}
                  className={checkboxClass}
                  onChange={(event) => onToggleAll?.(event.target.checked)}
                  ref={selectAll}
                  type="checkbox"
                />
              </th>
            )}
            {columns.map((column, index) => (
              <th className="px-4 py-2.5 font-medium" key={index} scope="col">
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
