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
    <div className={`flex flex-wrap items-center gap-2 text-sm ${className}`.trim()}>
      {showLabel && (
        <span aria-hidden="true" className="text-muted">
          {label}
        </span>
      )}
      <div
        aria-label={label}
        className="inline-flex items-center gap-0.5 rounded-full border border-line-strong bg-surface p-0.5"
        role="group"
      >
        {options.map((option) => {
          const pressed = option.value === value
          return (
            <button
              aria-pressed={pressed}
              className={`rounded-full px-3 py-1 text-body-sm transition max-md:min-h-11 ${
                pressed
                  ? 'bg-canvas font-semibold text-ink'
                  : 'font-medium text-subtle hover:text-ink'
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
    </div>
  )
}
