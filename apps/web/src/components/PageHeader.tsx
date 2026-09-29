import { type ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description?: string
  /** At most one secondary Button, on the right (SPEC 46, 7.1). */
  actions?: ReactNode
}

/** The one `<h1>` of a page, its subtitle and the header action slot. */
export function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-page-title">{title}</h1>
        {description && (
          <p className="mt-1 max-w-2xl text-body-sm text-subtle">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  )
}
