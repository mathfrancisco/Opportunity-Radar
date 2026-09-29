interface PageSizeSelectProps {
  id: string
  value: number
  onChange: (pageSize: number) => void
  /** Sizes offered; keep them within what the endpoint accepts (Inbox 200, companies 100). */
  options?: readonly number[]
  className?: string
}

const defaultOptions = [10, 25, 50, 100] as const

/** "Itens por página" as a native select with a visible label. Not wired to any screen yet. */
export function PageSizeSelect({
  id,
  value,
  onChange,
  options = defaultOptions,
  className = '',
}: PageSizeSelectProps) {
  return (
    <div className={`inline-flex items-center gap-2 text-caption text-muted ${className}`.trim()}>
      <label htmlFor={id}>Itens por página</label>
      <select
        className="h-8 rounded-control border border-line-strong bg-surface px-2 text-body-sm text-ink max-md:h-11"
        id={id}
        onChange={(event) => onChange(Number(event.target.value))}
        value={value}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  )
}
