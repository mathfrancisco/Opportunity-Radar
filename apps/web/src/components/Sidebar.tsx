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

interface SidebarProps {
  /** Omitted on pages that are reached from a link rather than from the nav. */
  current?: NavigationPath
  /** Called when a link is followed, so the mobile drawer can close itself. */
  onNavigate?: () => void
}

/**
 * Logo + the three navigation groups. Layout (fixed column or drawer) is the shell's
 * business; this component only owns what is inside.
 */
export function Sidebar({ current, onNavigate }: SidebarProps) {
  return (
    <div className="flex h-full flex-col gap-6">
      <Link
        className="flex items-center gap-3 self-start rounded-control px-2 py-1"
        onClick={onNavigate}
        to="/"
      >
        <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-base font-black">
          ◉
        </span>
        <span className="text-section tracking-tight">Opportunity Radar</span>
      </Link>
      <nav aria-label="Navegação principal">
        <ul className="flex flex-col gap-5">
          {navigation.map((group) => (
            <li key={group.id}>
              <p className="px-3 text-caption text-muted" id={`nav-${group.id}`}>
                {group.label}
              </p>
              <ul aria-labelledby={`nav-${group.id}`} className="mt-1 flex flex-col gap-1">
                {group.items.map((item) => {
                  const active = item.to === current
                  return (
                    <li key={item.to}>
                      <Link
                        aria-current={active ? 'page' : undefined}
                        className={`flex items-center gap-2 whitespace-nowrap rounded-control border px-3 text-sm max-md:min-h-11 md:h-9 ${
                          active
                            ? 'border-line bg-surface font-semibold text-ink'
                            : 'border-transparent font-medium text-subtle hover:bg-line hover:text-ink'
                        }`}
                        onClick={onNavigate}
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
      </nav>
    </div>
  )
}
