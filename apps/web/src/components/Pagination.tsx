interface PaginationProps {
  /** 1-based current page. Out-of-range values are clamped to the existing pages. */
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  /** Plural noun after the count: "Exibindo 1 a 15 de 145 oportunidades". */
  itemLabel?: string
  /** Names the `nav` landmark; change it when a screen has two paginations. */
  label?: string
  className?: string
}

type PageItem = number | 'gap-start' | 'gap-end'

/**
 * The page numbers to draw: first, last, the current one and one neighbour on each side,
 * with a gap where numbers are skipped — `1 … 4 5 6 … 12`. A gap that would hide a single
 * page draws that page instead: an ellipsis standing in for one number is longer than it.
 */
function pageWindow(page: number, totalPages: number): PageItem[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1)
  const start = Math.max(2, Math.min(page - 1, totalPages - 4))
  const end = Math.min(totalPages - 1, Math.max(page + 1, 5))
  const items: PageItem[] = [1]
  if (start > 2) items.push(start === 3 ? 2 : 'gap-start')
  for (let number = start; number <= end; number += 1) items.push(number)
  if (end < totalPages - 1) items.push(end === totalPages - 2 ? totalPages - 1 : 'gap-end')
  items.push(totalPages)
  return items
}

const buttonBase =
  'inline-flex h-8 min-w-8 items-center justify-center rounded-control border px-2 text-body-sm ' +
  'transition disabled:cursor-not-allowed disabled:opacity-40 max-md:h-11 max-md:min-w-11'

/**
 * "Exibindo X a Y de N" and the numbered pages.
 *
 * The count is a polite live region so a screen reader hears the new range when the page
 * changes; it never interrupts. The current page is marked by `aria-current`, and by border
 * *and* weight — never colour alone. With no items there is nothing to page through, so only
 * the count line is drawn.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  itemLabel = 'itens',
  label = 'Paginação',
  className = '',
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const current = Math.min(Math.max(1, page), totalPages)
  const from = total === 0 ? 0 : (current - 1) * pageSize + 1
  const to = Math.min(total, current * pageSize)

  return (
    <nav
      aria-label={label}
      className={`flex flex-wrap items-center justify-between gap-3 ${className}`.trim()}
    >
      <p aria-live="polite" className="text-caption text-muted">
        {total === 0 ? `Nenhum ${itemLabel === 'itens' ? 'item' : 'resultado'}` : `Exibindo ${from} a ${to} de ${total} ${itemLabel}`}
      </p>
      {total > 0 && (
        <ol className="flex flex-wrap items-center gap-1">
          <li>
            <button
              aria-label="Página anterior"
              className={`${buttonBase} border-line-strong bg-surface text-ink hover:border-ink`}
              disabled={current <= 1}
              onClick={() => onPageChange(current - 1)}
              type="button"
            >
              <span aria-hidden="true">‹</span>
            </button>
          </li>
          {pageWindow(current, totalPages).map((item) => (
            <li key={item}>
              {typeof item === 'string' ? (
                <span aria-hidden="true" className="inline-flex h-8 min-w-8 items-center justify-center text-muted">
                  …
                </span>
              ) : (
                <button
                  aria-current={item === current ? 'page' : undefined}
                  aria-label={`Página ${item}`}
                  className={`${buttonBase} ${
                    item === current
                      ? 'border-accent font-semibold text-accent-ink'
                      : 'border-transparent text-ink hover:border-line-strong'
                  }`}
                  onClick={() => onPageChange(item)}
                  type="button"
                >
                  {item}
                </button>
              )}
            </li>
          ))}
          <li>
            <button
              aria-label="Próxima página"
              className={`${buttonBase} border-line-strong bg-surface text-ink hover:border-ink`}
              disabled={current >= totalPages}
              onClick={() => onPageChange(current + 1)}
              type="button"
            >
              <span aria-hidden="true">›</span>
            </button>
          </li>
        </ol>
      )}
    </nav>
  )
}
