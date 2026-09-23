import { type ReactNode } from 'react'

/*
 * A forma do que vai chegar, no lugar onde vai chegar.
 *
 * A faixa "Carregando…" tinha cinco linhas de altura e dava lugar a uma lista de dez
 * cartões: a página pulava quando o dado chegava, e pulava diferente em cada tela. Um
 * esqueleto tem a mesma forma do conteúdo que substitui — mesmo raio, mesmo espaçamento,
 * mesma grade —, então o conteúdo aparece onde o esqueleto estava.
 *
 * O esqueleto é só visual. O anúncio continua sendo um `role="status"` por região, com o
 * mesmo texto que a faixa dizia: cada peça fica fora da árvore de acessibilidade, ou o
 * leitor de tela diria "carregando" uma vez por cartão.
 *
 * Bloco curto — um registro, um painel — continua com `LoadingState`: a faixa já tem mais
 * ou menos a altura dele, e um esqueleto ali seria forma inventada.
 */

interface SkeletonProps {
  /** What a screen reader hears, once for the whole region. */
  label: string
  children: ReactNode
  className?: string
}

export function Skeleton({ label, children, className = '' }: SkeletonProps) {
  return (
    <div aria-busy="true" className={className || undefined} role="status">
      <span className="sr-only">{label}</span>
      {/* Com movimento reduzido, a forma fica e a pulsação some. */}
      <div aria-hidden="true" className="motion-safe:animate-pulse">
        {children}
      </div>
    </div>
  )
}

/** One line of text that has not arrived yet. Width says how long the text usually is. */
export function Bone({ className = '' }: { className?: string }) {
  return <span className={`block h-3 rounded-full bg-divider ${className}`.trim()} />
}

function range(count: number) {
  return Array.from({ length: count }, (_, index) => index)
}

/** The list of cards of the Inbox and of the sources screen, count line included. */
export function CardListSkeleton({ label, count = 4 }: { label: string; count?: number }) {
  return (
    <Skeleton label={label}>
      <div className="grid gap-3">
        <Bone className="my-1 w-40" />
        {range(count).map((index) => (
          <div className="rounded-2xl border border-line bg-surface p-5" key={index}>
            <Bone className="h-4 w-2/3" />
            <Bone className="mt-3 w-1/3" />
            <Bone className="mt-4 w-5/6" />
          </div>
        ))}
      </div>
    </Skeleton>
  )
}

/** Rows under a real-looking header, for data that lives in a table. */
export function TableSkeleton({
  label,
  columns,
  rows = 5,
}: {
  label: string
  columns: number
  rows?: number
}) {
  return (
    <Skeleton label={label}>
      <div className="overflow-hidden rounded-2xl border border-line">
        <div className="flex gap-6 bg-canvas px-4 py-3">
          {range(columns).map((column) => (
            <Bone className="h-2.5 flex-1" key={column} />
          ))}
        </div>
        {range(rows).map((row) => (
          <div className="flex gap-6 border-t border-divider bg-surface px-4 py-4" key={row}>
            {range(columns).map((column) => (
              <Bone className={column === 0 ? 'flex-1' : 'flex-1 opacity-60'} key={column} />
            ))}
          </div>
        ))}
      </div>
    </Skeleton>
  )
}

/** A panel of `columns` label-over-value pairs, like the coverage strip of the sources screen. */
export function PanelSkeleton({ label, columns = 3 }: { label: string; columns?: number }) {
  return (
    <Skeleton label={label}>
      <div className="grid gap-3 rounded-2xl border border-line bg-panel p-5 text-sm sm:grid-cols-3">
        {range(columns).map((column) => (
          <div className="py-1" key={column}>
            <Bone className="w-24" />
            <Bone className="mt-2.5 w-32" />
          </div>
        ))}
      </div>
    </Skeleton>
  )
}
