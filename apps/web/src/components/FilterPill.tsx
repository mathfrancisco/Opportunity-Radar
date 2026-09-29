import { type ReactNode } from 'react'
import { ChevronDownIcon, FilterIcon } from './icons'

export interface FilterPillOption {
  value: string
  label: string
}

interface FilterPillProps {
  id: string
  /** Visible, and the accessible name of the select through `<label for>`. */
  label: string
  value: string
  /** The value that means "no filter". Any other value paints the pill as active. */
  defaultValue?: string
  options: readonly FilterPillOption[]
  onChange: (value: string) => void
  /** Decorative icon on the left; a funnel when omitted. */
  icon?: ReactNode
  className?: string
}

/**
 * A filter as a pill: icon, visible label, current value, chevron.
 *
 * The control is a native `<select>` (SPEC 46, D3): keyboard, screen reader, the mobile
 * picker and `getByLabel` in the tests all come for free. Only the closed state is styled;
 * the open list belongs to the OS (R2). The active state is a darker border *and* a bolder
 * label — colour alone would not say "this filter is on".
 */
export function FilterPill({
  id,
  label,
  value,
  defaultValue = '',
  options,
  onChange,
  icon,
  className = '',
}: FilterPillProps) {
  const active = value !== defaultValue
  return (
    <div
      className={`relative inline-flex h-8 items-center gap-1.5 rounded-control border bg-surface pl-2.5 text-body-sm focus-within:outline focus-within:outline-3 focus-within:outline-offset-3 focus-within:outline-ink max-md:h-11 ${
        active ? 'border-ink' : 'border-line-strong hover:border-ink'
      } ${className}`.trim()}
      data-active={active}
    >
      <span aria-hidden="true" className="text-muted">
        {icon ?? <FilterIcon />}
      </span>
      <label className={active ? 'font-semibold text-ink' : 'text-muted'} htmlFor={id}>
        {label}
      </label>
      <select
        className="h-full min-w-0 cursor-pointer appearance-none bg-transparent pr-8 pl-1 font-medium text-ink outline-none"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <span aria-hidden="true" className="pointer-events-none absolute right-2.5 text-muted">
        <ChevronDownIcon />
      </span>
    </div>
  )
}
