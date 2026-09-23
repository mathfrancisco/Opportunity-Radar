import { type ReactNode } from 'react'
import { Link } from 'react-router-dom'

const navigation = [
  { to: '/', label: 'Visão geral' },
  { to: '/inbox', label: 'Oportunidades' },
  { to: '/applications', label: 'Candidaturas' },
  { to: '/companies', label: 'Empresas' },
  { to: '/sources', label: 'Fontes' },
  { to: '/profile', label: 'Perfil' },
  { to: '/status', label: 'Status' },
] as const

export type NavigationPath = (typeof navigation)[number]['to']

interface PageShellProps {
  /** Omitted on pages that are reached from a link rather than from the nav. */
  current?: NavigationPath
  eyebrow: string
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
}

export function PageShell({
  current,
  eyebrow,
  title,
  description,
  children,
  footer,
}: PageShellProps) {
  return (
    <main className="min-h-screen bg-canvas px-5 py-7 text-ink sm:px-10 sm:py-10">
      {/* Primeiro alvo de tabulação: sete links de navegação antes do conteúdo, em toda
          página, é o que torna o teclado inutilizável sem isto. */}
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-6 focus:top-6 focus:z-10 focus:rounded-xl focus:bg-ink focus:px-5 focus:py-3 focus:text-sm focus:font-semibold focus:text-surface"
        href="#conteudo"
      >
        Pular para o conteúdo
      </a>
      <div className="mx-auto min-h-[calc(100vh-3.5rem)] max-w-5xl rounded-shell border border-line-soft bg-raised p-7 shadow-shell sm:p-12">
        <header
          className="flex flex-wrap items-center justify-between gap-4"
          aria-label="Opportunity Radar"
        >
          <Link className="flex items-center gap-3" to="/">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-accent text-lg font-black">
              ◉
            </span>
            <span className="text-section tracking-tight">Opportunity Radar</span>
          </Link>
          <nav aria-label="Navegação principal" className="flex flex-wrap gap-4 text-sm font-medium">
            {navigation.map((item) =>
              item.to === current ? (
                <Link
                  aria-current="page"
                  className="rounded-sm text-ink underline decoration-accent decoration-2 underline-offset-4"
                  key={item.to}
                  to={item.to}
                >
                  {item.label}
                </Link>
              ) : (
                <Link
                  className="rounded-sm text-subtle hover:text-ink"
                  key={item.to}
                  to={item.to}
                >
                  {item.label}
                </Link>
              ),
            )}
          </nav>
        </header>

        <section className="py-10 sm:py-14" id="conteudo" tabIndex={-1}>
          <p className="text-sm font-medium text-subtle">{eyebrow}</p>
          <h1 className="mt-2 text-display sm:text-display-lg">{title}</h1>
          {description && (
            <p className="mt-3 max-w-2xl text-body text-subtle">{description}</p>
          )}
          {children}
        </section>

        {footer && (
          <footer className="border-t border-line pt-5 text-sm text-muted">
            {footer}
          </footer>
        )}
      </div>
    </main>
  )
}
