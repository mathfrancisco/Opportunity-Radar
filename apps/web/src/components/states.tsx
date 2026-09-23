import { type ReactNode } from 'react'
import { Button } from './Button'

/*
 * Carregando, vazio, erro e conflito, uma vez só.
 *
 * Cada estado carrega o próprio anúncio: `role="status"` para o que é informação e
 * `role="alert"` para o que exige decisão. É por isso que as rotas não precisam mais
 * envolver tudo num `aria-live` — uma região viva em volta de uma tabela inteira anuncia a
 * tabela inteira, que é ruído, e aninhada a um alerta ainda o anuncia duas vezes.
 *
 * Os quatro são distintos porque a recuperação é distinta: rede falhou, tente de novo; o
 * registro mudou, leia de novo antes de decidir; não há nada aqui, e isso pode ser normal.
 */

interface LoadingStateProps {
  /** Say what is loading: "Carregando fontes…" beats a spinner with no subject. */
  children: ReactNode
  className?: string
}

export function LoadingState({ children, className = '' }: LoadingStateProps) {
  return (
    <p
      className={`rounded-2xl bg-info-surface p-5 text-info-ink ${className}`.trim()}
      role="status"
    >
      {children}
    </p>
  )
}

interface EmptyStateProps {
  children: ReactNode
  className?: string
}

/**
 * Nothing to show, which is a result and not a failure.
 *
 * A block rather than a paragraph because some empty states carry the action that fills
 * them — an opportunity with no candidacy offers to start one right there.
 */
export function EmptyState({ children, className = '' }: EmptyStateProps) {
  return (
    <div
      className={`rounded-2xl border border-dashed border-line-strong p-5 text-subtle ${className}`.trim()}
      role="status"
    >
      {children}
    </div>
  )
}

interface ErrorStateProps {
  children: ReactNode
  /** Omitted when nothing can be retried, in which case no button is offered. */
  onRetry?: () => void
  retryLabel?: string
  className?: string
}

export function ErrorState({
  children,
  onRetry,
  retryLabel = 'Tentar novamente',
  className = '',
}: ErrorStateProps) {
  return (
    <div
      className={`rounded-2xl bg-danger-surface-strong p-5 text-danger-ink ${className}`.trim()}
      role="alert"
    >
      <p>{children}</p>
      {onRetry && (
        <Button className="mt-3" onClick={onRetry} size="sm" variant="secondary">
          {retryLabel}
        </Button>
      )}
    </div>
  )
}

interface ConflictNoticeProps {
  children: ReactNode
  /** Re-reads the record. The one recovery a conflict accepts. */
  onReload?: () => void
  reloadLabel?: string
  className?: string
}

export function ConflictNotice({
  children,
  onReload,
  reloadLabel = 'Recarregar o registro',
  className = '',
}: ConflictNoticeProps) {
  return (
    <div
      className={`rounded-2xl border border-warning-line bg-warning-surface p-5 text-warning-ink ${className}`.trim()}
      role="alert"
    >
      <p>{children}</p>
      {onReload && (
        <Button className="mt-3" onClick={onReload} size="sm" variant="secondary">
          {reloadLabel}
        </Button>
      )}
    </div>
  )
}
