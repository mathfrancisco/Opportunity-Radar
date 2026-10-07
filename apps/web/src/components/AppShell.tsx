import { type ReactNode, useRef, useState } from 'react'
import { PageHeader } from './PageHeader'
import { Sidebar, type NavigationPath } from './Sidebar'
import { MobileNavigationDialog } from './ui/MobileNavigationDialog'

export interface AppShellProps {
  /** Omitted on pages that are reached from a link rather than from the nav. */
  current?: NavigationPath
  /** Petrol kicker above the title (SPEC 54: "Decidir"); drawn only when given. */
  eyebrow?: string
  title: string
  description?: string
  /** Back link, drawn above the title block. */
  back?: ReactNode
  /** Facts that belong to the title block (meta line, chips), drawn under the title. */
  meta?: ReactNode
  /** Header action slot: at most one secondary Button (SPEC 46, 7.1). */
  actions?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

const drawerId = 'sidebar'

/**
 * Sidebar + content on the canvas. From `md` up the sidebar is a fixed column; below it, it
 * is a drawer opened by the menu button.
 */
export function AppShell({
  current,
  eyebrow,
  title,
  description,
  back,
  meta,
  actions,
  children,
  footer,
}: AppShellProps) {
  const [open, setOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)

  return (
    <div className="min-h-screen bg-canvas text-ink md:flex">
      {/* Primeiro alvo de tabulação: sem isto, a sidebar inteira vem antes do conteúdo em
          toda página, o que torna o teclado inutilizável. */}
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-30 focus:rounded-control focus:bg-ink focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-surface"
        href="#conteudo"
      >
        Pular para o conteúdo
      </a>

      <div className="flex items-center gap-3 border-b border-line-strong bg-sidebar px-4 py-2 md:hidden">
        <MobileNavigationDialog
          contentClassName="fixed inset-y-0 left-0 z-20 w-60 overflow-y-auto border-r border-line-strong bg-sidebar p-3 shadow-overlay md:hidden"
          onOpenChange={setOpen}
          open={open}
          title="Navegação principal"
          trigger={
            <button
              aria-controls={drawerId}
              aria-expanded={open}
              className="min-h-11 rounded-control border border-line-strong bg-surface px-4 text-sm font-medium"
              ref={menuButton}
              type="button"
            >
              Menu
            </button>
          }
        >
          <Sidebar current={current} onNavigate={() => setOpen(false)} />
        </MobileNavigationDialog>
      </div>

      <aside
        className="hidden w-60 shrink-0 border-r border-line-strong bg-sidebar p-3 md:sticky md:top-0 md:block md:h-screen md:overflow-y-auto"
      >
        <Sidebar current={current} />
      </aside>

      <main className="min-w-0 flex-1 p-4 md:p-8">
        <div className="min-h-[calc(100vh-4rem)]">
          <section id="conteudo" tabIndex={-1}>
            {back && <div className="mb-4">{back}</div>}
            <PageHeader
              actions={actions}
              description={description}
              eyebrow={eyebrow}
              meta={meta}
              title={title}
            />
            <div className="mt-6">{children}</div>
          </section>
          {footer && (
            <footer className="mt-8 border-t border-line pt-5 text-sm text-muted">
              {footer}
            </footer>
          )}
        </div>
      </main>
    </div>
  )
}
