import { type ReactNode, useCallback, useEffect, useRef, useState } from 'react'
import { PageHeader } from './PageHeader'
import { Sidebar, type NavigationPath } from './Sidebar'

export interface AppShellProps {
  /** Omitted on pages that are reached from a link rather than from the nav. */
  current?: NavigationPath
  /** Kept for API compatibility with the old shell; no longer shown (SPEC 46, D10). */
  eyebrow?: string
  title: string
  description?: string
  /** Header action slot: at most one secondary Button (SPEC 46, 7.1). */
  actions?: ReactNode
  children: ReactNode
  footer?: ReactNode
}

const drawerId = 'sidebar'

/**
 * Sidebar + white content panel. From `md` up the sidebar is a fixed column; below it, it
 * is a drawer opened by the menu button.
 */
export function AppShell({ current, title, description, actions, children, footer }: AppShellProps) {
  const [open, setOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false)
    if (restoreFocus) menuButton.current?.focus()
  }, [])

  useEffect(() => {
    if (!open) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') close(true)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, close])

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

      <div className="flex items-center gap-3 border-b border-line px-4 py-2 md:hidden">
        <button
          aria-controls={drawerId}
          aria-expanded={open}
          className="min-h-11 rounded-control border border-line-strong bg-surface px-4 text-sm font-medium"
          onClick={() => setOpen((value) => !value)}
          ref={menuButton}
          type="button"
        >
          Menu
        </button>
      </div>

      {open && (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-10 bg-ink/30 md:hidden"
          data-testid="drawer-backdrop"
          onClick={() => close(false)}
        />
      )}
      <aside
        className={`${
          open ? 'fixed inset-y-0 left-0 z-20 block overflow-y-auto' : 'hidden'
        } w-60 shrink-0 border-r border-line bg-canvas p-3 md:sticky md:top-0 md:block md:h-screen md:overflow-y-auto md:border-r-0`}
        id={drawerId}
      >
        <Sidebar current={current} onNavigate={() => close(false)} />
      </aside>

      <main className="min-w-0 flex-1 md:p-3 md:pl-0">
        <div className="min-h-[calc(100vh-1.5rem)] border-line bg-surface p-4 md:rounded-panel md:border md:p-6">
          <section id="conteudo" tabIndex={-1}>
            <PageHeader actions={actions} description={description} title={title} />
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
