import { type ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description?: string
  /** Small petrol kicker above the title ("Decidir"); nothing is drawn when absent. */
  eyebrow?: string
  /** Facts that belong to the title (meta line, chips), drawn under the description. */
  meta?: ReactNode
  /** At most one secondary Button, on the right (SPEC 46, 7.1). */
  actions?: ReactNode
}

/** The one `<h1>` of a page, its kicker, subtitle and the header action slot. */
export function PageHeader({ title, description, eyebrow, meta, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        {eyebrow && <p className="mb-1 text-caption font-semibold text-accent-ink">{eyebrow}</p>}
        <h1 className="text-page-title">{title}</h1>
        {description && (
          <p className="mt-1 max-w-2xl text-body-sm text-subtle">{description}</p>
        )}
        {meta}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
