import { type ReactNode } from 'react'
import { Link } from 'react-router-dom'

const navigation = [
  { to: '/', label: 'Visão geral' },
  { to: '/inbox', label: 'Oportunidades' },
  { to: '/companies', label: 'Empresas' },
  { to: '/status', label: 'Status' },
] as const

export type NavigationPath = (typeof navigation)[number]['to']

interface PageShellProps {
  current: NavigationPath
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
    <main className="min-h-screen bg-[#f2f5ef] px-5 py-7 text-[#17322d] sm:px-10 sm:py-10">
      <div className="mx-auto min-h-[calc(100vh-3.5rem)] max-w-5xl rounded-[2rem] border border-[#ced8ce] bg-[#fbfcf8] p-7 shadow-[0_24px_70px_rgba(23,50,45,0.10)] sm:p-12">
        <header
          className="flex flex-wrap items-center justify-between gap-4"
          aria-label="Opportunity Radar"
        >
          <Link className="flex items-center gap-3" to="/">
            <span className="grid h-10 w-10 place-items-center rounded-full bg-[#d7f06f] text-lg font-black">
              ◉
            </span>
            <span className="text-lg font-semibold tracking-tight">Opportunity Radar</span>
          </Link>
          <nav aria-label="Navegação principal" className="flex flex-wrap gap-4 text-sm font-medium">
            {navigation.map((item) =>
              item.to === current ? (
                <Link
                  aria-current="page"
                  className="text-[#17322d] underline decoration-[#d7f06f] decoration-2 underline-offset-4"
                  key={item.to}
                  to={item.to}
                >
                  {item.label}
                </Link>
              ) : (
                <Link className="text-[#547068] hover:text-[#17322d]" key={item.to} to={item.to}>
                  {item.label}
                </Link>
              ),
            )}
          </nav>
        </header>

        <section className="py-10 sm:py-14">
          <p className="text-sm font-medium text-[#547068]">{eyebrow}</p>
          <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] sm:text-5xl">{title}</h1>
          {description && (
            <p className="mt-3 max-w-2xl leading-7 text-[#547068]">{description}</p>
          )}
          {children}
        </section>

        {footer && (
          <footer className="border-t border-[#dce4dc] pt-5 text-sm text-[#6d827b]">
            {footer}
          </footer>
        )}
      </div>
    </main>
  )
}
