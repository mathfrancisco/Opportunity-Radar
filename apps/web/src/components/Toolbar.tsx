interface ToolbarOption<T extends string> {
  value: T
  label: string
}

interface ToolbarProps<T extends string> {
  /** Names the group for assistive tech; shown beside the buttons when `showLabel` is set. */
  label: string
  showLabel?: boolean
  options: readonly ToolbarOption<T>[]
  value: T | undefined
  onChange: (value: T) => void
  className?: string
}

/**
 * A row of mutually exclusive filters, each a button that says whether it is pressed.
 *
 * The Inbox's application filter and the Overview's metrics window were the same markup
 * twice. It is a `group`, not a `toolbar`: the ARIA toolbar promises arrow-key movement
 * between items, and these are ordinary tab stops.
 */
export function Toolbar<T extends string>({
  label,
  showLabel = false,
  options,
  value,
  onChange,
  className = '',
}: ToolbarProps<T>) {
  return (
    <div
      aria-label={label}
      className={`flex flex-wrap items-center gap-2 text-sm ${className}`.trim()}
      role="group"
    >
      {showLabel && (
        <span aria-hidden="true" className="mr-1 text-muted">
          {label}
        </span>
      )}
      {options.map((option) => {
        const pressed = option.value === value
        return (
          <button
            aria-pressed={pressed}
            className={`rounded-full border px-4 py-2 transition ${
              pressed
                ? 'border-ink bg-ink font-semibold text-surface focus-visible:outline-accent'
                : 'border-line-strong bg-surface font-medium hover:border-ink'
            }`}
            key={option.value}
            onClick={() => onChange(option.value)}
            type="button"
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
