import { type FormEvent } from 'react'
import { SearchIcon } from './icons'

interface SearchInputProps {
  id: string
  label: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  /** Called on Enter or on a click on the magnifier. The page reload is already prevented. */
  onSubmit: () => void
  /** Accessible name of the submit button. Never visible (SPEC 46, D11). */
  action?: string
  /** Fills its container instead of the fixed `md` width, for a toolbar that sizes it. */
  fullWidth?: boolean
  className?: string
}

/**
 * The search field of the filter row: a magnifier and a text field.
 *
 * There is no visible "Buscar" button (D11). The magnifier *is* the button — clickable, and
 * named "Buscar" for assistive tech through a `sr-only` label — and Enter in the field
 * submits the form. Replaced the old `SearchBar`, now removed.
 */
export function SearchInput({
  id,
  label,
  placeholder,
  value,
  onChange,
  onSubmit,
  action = 'Buscar',
  fullWidth = false,
  className = '',
}: SearchInputProps) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  return (
    <form
      className={`relative flex w-full items-center ${fullWidth ? '' : 'md:w-80'} ${className}`.trim()}
      onSubmit={submit}
      role="search"
    >
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <button
        className="absolute left-1 flex h-6 w-8 items-center justify-center text-muted hover:text-ink max-md:h-9"
        type="submit"
      >
        <SearchIcon />
        <span className="sr-only">{action}</span>
      </button>
      <input
        className="h-8 w-full min-w-0 rounded-control border border-control-line bg-surface pr-3 pl-9 text-body-sm text-ink placeholder:text-muted max-md:h-11"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type="search"
        value={value}
      />
    </form>
  )
}
