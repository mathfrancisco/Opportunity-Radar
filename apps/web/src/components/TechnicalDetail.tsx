import { type ReactNode } from 'react'

/** Technical codes live here, collapsed, and nowhere else on a screen. */
export function TechnicalDetail({ children }: { children: ReactNode }) {
  return (
    <details className="mt-1 text-caption text-subtle">
      <summary className="cursor-pointer">Detalhe técnico</summary>
      <div className="break-anywhere mt-1">{children}</div>
    </details>
  )
}
