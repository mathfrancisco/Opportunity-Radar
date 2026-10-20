import { Link } from 'react-router-dom'
import { BrandMark } from './ui/BrandMark'
import { ThemeToggle } from './ui/ThemeToggle'
import {
  ApplicationsIcon,
  CompaniesIcon,
  HomologationIcon,
  InboxIcon,
  OverviewIcon,
  ProfileIcon,
  SourcesIcon,
  StatusIcon,
} from './icons'

export type NavigationPath =
  | '/'
  | '/inbox'
  | '/applications'
  | '/companies'
  | '/sources'
  | '/sources/homologation-queue'
  | '/profile'
  | '/status'

interface SidebarProps {
  /** Omitted on pages that are reached from a link rather than from the nav. */
  current?: NavigationPath
  /** Called when a link is followed, so the mobile drawer can close itself. */
  onNavigate?: () => void
  /** Owner links stay hidden unless a server-verified owner capability is available. */
  isOwner?: boolean
}

/**
 * Logo + the navigation groups. Layout (fixed column or drawer) is the shell's
 * business; this component only owns what is inside.
 */
export function Sidebar({ current, onNavigate, isOwner = false }: SidebarProps) {
  const navigation = [
    {
      id: 'decidir',
      label: 'Decidir',
      items: [
        { to: '/' as const, label: 'Visão geral', icon: <OverviewIcon /> },
        { to: '/inbox' as const, label: 'Inbox', icon: <InboxIcon /> },
        { to: '/applications' as const, label: 'Pipeline', icon: <ApplicationsIcon /> },
      ],
    },
    ...(isOwner
      ? [{ id: 'pesquisar', label: 'Pesquisar', items: [{ to: '/companies' as const, label: 'Empresas', icon: <CompaniesIcon /> }] }]
      : []),
    {
      id: 'operar',
      label: 'Operar',
      items: [
        ...(isOwner
          ? [
              { to: '/sources' as const, label: 'Fontes', icon: <SourcesIcon /> },
              { to: '/sources/homologation-queue' as const, label: 'Homologação', icon: <HomologationIcon /> },
            ]
          : []),
        { to: '/profile' as const, label: 'Perfil', icon: <ProfileIcon /> },
        ...(isOwner ? [{ to: '/status' as const, label: 'Status', icon: <StatusIcon /> }] : []),
      ],
    },
  ]

  return (
    <div className="flex h-full flex-col gap-6">
      <Link
        className="flex items-center gap-3 self-start rounded-control px-2 py-1"
        onClick={onNavigate}
        to="/"
      >
        <BrandMark />
      </Link>
      <nav aria-label="Navegação principal">
        <ul className="flex flex-col gap-5">
          {navigation.map((group) => (
            <li key={group.id}>
              <p className="px-3 text-caption font-semibold text-muted" id={`nav-${group.id}`}>
                {group.label}
              </p>
              <ul aria-labelledby={`nav-${group.id}`} className="mt-1 flex flex-col gap-1">
                {group.items.map((item) => {
                  const active = item.to === current
                  return (
                    <li key={item.to}>
                      <Link
                        aria-current={active ? 'page' : undefined}
                        className={`flex items-center gap-2 whitespace-nowrap rounded-control px-3 text-sm max-md:min-h-11 md:h-9 ${
                          active
                            ? 'bg-surface font-semibold text-ink shadow-[inset_3px_0_0_var(--color-accent)]'
                            : 'font-medium text-subtle hover:bg-surface hover:text-ink'
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
      <div className="mt-auto flex flex-col gap-3">
        <p className="px-2 text-caption text-subtle">Nenhum recrutador vê seu perfil aqui.</p>
        <ThemeToggle />
      </div>
    </div>
  )
}
