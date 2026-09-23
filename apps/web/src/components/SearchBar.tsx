import { type FormEvent } from 'react'
import { Button } from './Button'

interface SearchBarProps {
  id: string
  label: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  action?: string
}

/** The search row of the Inbox and of the company list, which were the same markup twice. */
export function SearchBar({
  id,
  label,
  placeholder,
  value,
  onChange,
  onSubmit,
  action = 'Buscar',
}: SearchBarProps) {
  return (
    <form className="mt-8 flex max-w-xl gap-3" onSubmit={onSubmit} role="search">
      <label className="sr-only" htmlFor={id}>
        {label}
      </label>
      <input
        className="min-w-0 flex-1 rounded-xl border border-line-strong bg-surface px-4 py-3 outline-none focus:border-ink focus:ring-2 focus:ring-accent"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
      <Button type="submit">{action}</Button>
    </form>
  )
}
