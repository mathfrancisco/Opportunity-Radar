export function BrandSymbol({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={['text-brand', className].filter(Boolean).join(' ')}
    >
      <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="16" cy="16" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="16" cy="16" r="4" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="21.5" cy="11" r="2.8" className="fill-nugget" />
    </svg>
  )
}

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      role="img"
      aria-label="Bateia"
      className={['inline-flex items-center gap-2', className].filter(Boolean).join(' ')}
    >
      <BrandSymbol />
      <span className="font-display text-2xl leading-none text-ink">bateia</span>
    </span>
  )
}
