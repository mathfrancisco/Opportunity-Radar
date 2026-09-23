import { type ReactNode, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import {
  ApplicationsIcon,
  CompaniesIcon,
  InboxIcon,
  OverviewIcon,
  ProfileIcon,
  SourcesIcon,
  StatusIcon,
} from './icons'

/*
 * As sete telas agrupadas pelo que servem: o trabalho de todo dia, o catálogo que o
 * alimenta, e o diagnóstico. Uma lista plana dava o mesmo peso à tela mais usada e à menos
 * usada, e era lida item a item, toda vez.
 */
const navigation = [
  {
    id: 'diario',
    label: 'Dia a dia',
    items: [
      { to: '/', label: 'Visão geral', icon: <OverviewIcon /> },
      { to: '/inbox', label: 'Oportunidades', icon: <InboxIcon /> },
      { to: '/applications', label: 'Candidaturas', icon: <ApplicationsIcon /> },
    ],
  },
  {
    id: 'catalogo',
    label: 'Catálogo',
    items: [
      { to: '/companies', label: 'Empresas', icon: <CompaniesIcon /> },
      { to: '/sources', label: 'Fontes', icon: <SourcesIcon /> },
      { to: '/profile', label: 'Perfil', icon: <ProfileIcon /> },
    ],
  },
  {
    id: 'diagnostico',
    label: 'Diagnóstico',
    items: [{ to: '/status', label: 'Status', icon: <StatusIcon /> }],
  },
] as const

export type NavigationPath = (typeof navigation)[number]['items'][number]['to']

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
  const scrollerRef = useRef<HTMLDivElement>(null)

  // Em tela estreita a barra rola na horizontal, e a seção ativa pode nascer fora da vista.
  // Trazê-la para dentro é o que impede a barra de esconder justamente onde o operador está.
  useEffect(() => {
    const scroller = scrollerRef.current
    const active = scroller?.querySelector<HTMLElement>('[aria-current="page"]')
    if (!scroller || !active) return
    const start = active.offsetLeft
    const end = start + active.offsetWidth
    if (start < scroller.scrollLeft || end > scroller.scrollLeft + scroller.clientWidth) {
      scroller.scrollLeft = Math.max(0, start - 16)
    }
  }, [current])

  return (
    <main className="min-h-screen bg-canvas px-5 py-7 text-ink sm:px-10 sm:py-10">
      {/* Primeiro alvo de tabulação: oito links de cabeçalho antes do conteúdo, em toda
          página, é o que torna o teclado inutilizável sem isto. */}
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:left-6 focus:top-6 focus:z-10 focus:rounded-xl focus:bg-ink focus:px-5 focus:py-3 focus:text-sm focus:font-semibold focus:text-surface"
        href="#conteudo"
      >
        Pular para o conteúdo
      </a>
      <div className="mx-auto min-h-[calc(100vh-3.5rem)] max-w-5xl rounded-shell border border-line-soft bg-raised p-7 shadow-shell sm:p-12">
        <header
          className="flex flex-col gap-6"
          aria-label="Opportunity Radar"
        >
          <Link className="flex items-center gap-3 self-start" to="/">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-accent text-lg font-black">
              ◉
            </span>
            <span className="text-section tracking-tight">Opportunity Radar</span>
          </Link>
          <nav aria-label="Navegação principal" className="w-full">
            <div
              className="relative -mx-2 overflow-x-auto px-2 pb-2 [scrollbar-width:thin]"
              ref={scrollerRef}
            >
              <ul className="flex gap-6 sm:gap-8">
                {navigation.map((group) => (
                  <li className="shrink-0" key={group.id}>
                    <p
                      className="px-3 text-overline uppercase text-muted"
                      id={`nav-${group.id}`}
                    >
                      {group.label}
                    </p>
                    <ul aria-labelledby={`nav-${group.id}`} className="mt-2 flex gap-1">
                      {group.items.map((item) => {
                        const active = item.to === current
                        return (
                          <li key={item.to}>
                            <Link
                              aria-current={active ? 'page' : undefined}
                              className={`flex min-h-10 items-center gap-2 whitespace-nowrap rounded-full px-3 text-sm transition ${
                                active
                                  ? 'bg-ink font-semibold text-surface focus-visible:outline-accent'
                                  : 'font-medium text-subtle hover:bg-panel hover:text-ink'
                              }`}
                              to={item.to}
                            >
                              {item.icon}
                              {item.label}
                            </Link>
                          </li>
                        )
                      })}
                    </ul>
                  </li>
                ))}
              </ul>
            </div>
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
