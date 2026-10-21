import { type CSSProperties, type KeyboardEvent, type ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
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
  /** Locks the select; the visible value stays whatever `value` selects. */
  disabled?: boolean
  /** Accessible description of the pill (why it is locked, for instance). */
  description?: string
  /**
   * `pill` keeps the compact filter chip used by list toolbars. `field` gives dense
   * filter forms a label and a full-width select, so the selected value has room to read.
   */
  variant?: 'pill' | 'field'
}

/**
 * A filter as a pill: icon, visible label, current value, chevron.
 *
 * The compact pill preserves the native select used in list toolbars. Inbox fields use a
 * themed combobox so its menu stays legible in the product surface. Both expose the active
 * state with a darker border and bolder label, instead of relying on colour alone.
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
  disabled = false,
  description,
  variant = 'pill',
}: FilterPillProps) {
  const descriptionId = description ? `${id}-description` : undefined
  const active = value !== defaultValue
  const optionsList = options.map((option) => (
    <option key={option.value} value={option.value}>
      {option.label}
    </option>
  ))

  if (variant === 'field') {
    return (
      <FilterField
        active={active}
        className={className}
        description={description}
        descriptionId={descriptionId}
        disabled={disabled}
        id={id}
        label={label}
        onChange={onChange}
        options={options}
        value={value}
      />
    )
  }

  return (
    <div
      className={`relative inline-flex h-8 items-center gap-1.5 rounded-control border bg-surface pl-2.5 text-body-sm focus-within:outline focus-within:outline-3 focus-within:outline-offset-3 focus-within:outline-accent max-md:h-12 ${
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
        aria-describedby={descriptionId}
        disabled={disabled}
        id={id}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {optionsList}
      </select>
      {description ? (
        <span className="sr-only" id={descriptionId}>
          {description}
        </span>
      ) : null}
      <span aria-hidden="true" className="pointer-events-none absolute right-2.5 text-muted">
        <ChevronDownIcon />
      </span>
    </div>
  )
}

interface FilterFieldProps {
  active: boolean
  className: string
  description?: string
  descriptionId?: string
  disabled: boolean
  id: string
  label: string
  onChange: (value: string) => void
  options: readonly FilterPillOption[]
  value: string
}

function FilterField({
  active,
  className,
  description,
  descriptionId,
  disabled,
  id,
  label,
  onChange,
  options,
  value,
}: FilterFieldProps) {
  const [open, setOpen] = useState(false)
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === value))
  const [highlightedIndex, setHighlightedIndex] = useState(selectedIndex)
  const [popupStyle, setPopupStyle] = useState<CSSProperties>({})
  const buttonRef = useRef<HTMLButtonElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const typeaheadRef = useRef('')
  const typeaheadTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const generatedId = useId()
  const labelId = `${id}-label`
  const listboxId = `${id}-${generatedId}-listbox`
  const optionId = (index: number) => `${listboxId}-option-${index}`

  useEffect(() => {
    if (!open) return
    const dismiss = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', dismiss)
    return () => document.removeEventListener('pointerdown', dismiss)
  }, [open])

  useLayoutEffect(() => {
    if (!open) return
    const position = () => {
      const rect = buttonRef.current?.getBoundingClientRect()
      if (!rect) return
      const below = window.innerHeight - rect.bottom - 8
      const above = rect.top - 8
      const openAbove = below < 160 && above > below
      setPopupStyle({
        bottom: openAbove ? window.innerHeight - rect.top + 4 : undefined,
        left: rect.left,
        maxHeight: Math.max(96, Math.min(256, openAbove ? above : below)),
        position: 'fixed',
        top: openAbove ? undefined : rect.bottom + 4,
        width: rect.width,
      })
    }
    position()
    window.addEventListener('resize', position)
    window.addEventListener('scroll', position, true)
    return () => {
      window.removeEventListener('resize', position)
      window.removeEventListener('scroll', position, true)
    }
  }, [open])

  useEffect(() => {
    const list = listRef.current
    const option = document.getElementById(`${listboxId}-option-${highlightedIndex}`)
    if (!open || !list || !option) return
    if (option.offsetTop < list.scrollTop) list.scrollTop = option.offsetTop
    else if (option.offsetTop + option.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = option.offsetTop + option.offsetHeight - list.clientHeight
    }
  }, [highlightedIndex, listboxId, open])

  const close = (restoreFocus = false) => {
    setOpen(false)
    if (restoreFocus) requestAnimationFrame(() => buttonRef.current?.focus())
  }
  const choose = (index: number) => {
    const option = options[index]
    if (!option) return
    onChange(option.value)
    close(true)
  }
  const openList = (index = selectedIndex) => {
    setHighlightedIndex(index)
    setOpen(true)
  }
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return
    if (event.key === 'Tab') {
      close()
      return
    }
    if (event.key === 'Escape') {
      if (open) event.preventDefault()
      close(true)
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const current = open ? highlightedIndex : selectedIndex
      openList((current + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length)
      return
    }
    if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      openList(event.key === 'Home' ? 0 : options.length - 1)
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      if (open) choose(highlightedIndex)
      else openList()
      return
    }
    if (event.key.length === 1) {
      typeaheadRef.current += event.key.toLocaleLowerCase()
      clearTimeout(typeaheadTimer.current)
      typeaheadTimer.current = setTimeout(() => { typeaheadRef.current = '' }, 500)
      const match = options.findIndex((option) => option.label.toLocaleLowerCase().startsWith(typeaheadRef.current))
      if (match >= 0) {
        event.preventDefault()
        openList(match)
      }
    }
  }

  const selected = options[selectedIndex]
  return (
    <div className={`relative min-w-40 max-w-full ${className}`.trim()} data-active={active} data-disabled={disabled} ref={rootRef}>
      <span className={active ? 'text-caption font-semibold text-ink' : 'text-caption font-medium text-muted'} id={labelId}>
        {label}
      </span>
      <button
        aria-activedescendant={open ? optionId(highlightedIndex) : undefined}
        aria-controls={listboxId}
        aria-describedby={descriptionId}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-labelledby={`${labelId} ${id}-value`}
        className={`mt-1 flex h-9 w-full items-center justify-between rounded-control border bg-surface py-1.5 pr-3 pl-3 text-left text-body-sm outline-none focus-visible:outline focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent max-md:h-11 ${disabled ? 'cursor-not-allowed border-line text-muted' : active ? 'cursor-pointer border-ink text-ink' : 'cursor-pointer border-line text-ink hover:border-ink'}`}
        disabled={disabled}
        id={id}
        onClick={() => (open ? close() : openList())}
        onKeyDown={onKeyDown}
        ref={buttonRef}
        role="combobox"
        type="button"
      >
        <span className="truncate" id={`${id}-value`}>{selected?.label}</span>
        <span aria-hidden="true" className="ml-3 shrink-0 text-muted"><ChevronDownIcon /></span>
      </button>
      {open ? (
        <div className="z-30 w-full overflow-y-auto rounded-control border border-line bg-surface p-1 shadow-overlay" id={listboxId} ref={listRef} role="listbox" aria-labelledby={labelId} style={popupStyle}>
          {options.map((option, index) => (
            <button
              aria-selected={option.value === value}
              className={`flex min-h-10 w-full items-center justify-between rounded-control px-3 py-2 text-left text-body-sm outline-none focus-visible:bg-accent-surface ${index === highlightedIndex ? 'bg-accent-surface text-ink' : 'text-ink hover:bg-accent-surface'} ${option.value === value ? 'font-semibold text-accent-ink' : ''}`}
              data-value={option.value}
              id={optionId(index)}
              key={option.value}
              onClick={() => choose(index)}
              onMouseMove={() => setHighlightedIndex(index)}
              role="option"
              tabIndex={-1}
              type="button"
            >
              {option.label}<span aria-hidden="true">{option.value === value ? '✓' : ''}</span>
            </button>
          ))}
        </div>
      ) : null}
      {description ? <span className="sr-only" id={descriptionId}>{description}</span> : null}
    </div>
  )
}
