import { type ReactNode } from 'react'

/*
 * Um ícone por seção, desenhado aqui em vez de vir de uma biblioteca: são sete traços, e
 * uma dependência inteira para sete traços é peso sem decisão.
 *
 * Todo ícone é decorativo. Ele acompanha o rótulo e nunca o substitui, então fica fora da
 * árvore de acessibilidade — um leitor de tela que ouvisse "imagem, Fontes" a cada item
 * estaria ouvindo o rótulo duas vezes.
 */

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 shrink-0"
      fill="none"
      focusable="false"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={1.75}
      viewBox="0 0 24 24"
    >
      {children}
    </svg>
  )
}

export function OverviewIcon() {
  return (
    <Icon>
      <rect height="7" rx="1.5" width="7" x="3.5" y="3.5" />
      <rect height="7" rx="1.5" width="7" x="13.5" y="3.5" />
      <rect height="7" rx="1.5" width="7" x="3.5" y="13.5" />
      <rect height="7" rx="1.5" width="7" x="13.5" y="13.5" />
    </Icon>
  )
}

export function InboxIcon() {
  return (
    <Icon>
      <path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5" />
      <path d="M5.5 5.5h13l2 8v5a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1v-5z" />
    </Icon>
  )
}

export function ApplicationsIcon() {
  return (
    <Icon>
      <rect height="12" rx="1.5" width="17" x="3.5" y="7.5" />
      <path d="M8.5 7.5v-2a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1v2" />
      <path d="M3.5 12.5h17" />
    </Icon>
  )
}

export function CompaniesIcon() {
  return (
    <Icon>
      <path d="M4.5 20.5v-15a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v15" />
      <path d="M14.5 9.5h4a1 1 0 0 1 1 1v10" />
      <path d="M3 20.5h18" />
      <path d="M8 8.5h3M8 12.5h3M8 16.5h3" />
    </Icon>
  )
}

export function SourcesIcon() {
  return (
    <Icon>
      <circle cx="12" cy="12" r="1.5" />
      <path d="M8.5 15.5a5 5 0 0 1 0-7M15.5 8.5a5 5 0 0 1 0 7" />
      <path d="M5.5 18.5a9 9 0 0 1 0-13M18.5 5.5a9 9 0 0 1 0 13" />
    </Icon>
  )
}

export function ProfileIcon() {
  return (
    <Icon>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </Icon>
  )
}

export function StatusIcon() {
  return (
    <Icon>
      <path d="M3 12h4l2.5-6 5 12 2.5-6h4" />
    </Icon>
  )
}
