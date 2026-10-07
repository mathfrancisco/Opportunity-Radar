import { type ButtonHTMLAttributes, type ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary'
export type ButtonSize = 'md' | 'sm'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
}

const base =
  'inline-flex items-center justify-center gap-2 rounded-control text-sm transition ' +
  'disabled:cursor-not-allowed disabled:opacity-40 max-md:min-h-11'

// The focus ring is the global `:focus-visible` (3px `accent`, offset 3px; SPEC 54, 5.2): the
// ring sits outside the button, separated by the offset, so it stays visible against the
// petrol fill of the primary variant.
const variants: Record<ButtonVariant, string> = {
  primary: 'bg-accent font-semibold text-surface hover:bg-accent-hover',
  secondary: 'border border-line-strong bg-surface font-medium text-ink hover:border-ink',
}

const sizes: Record<ButtonSize, string> = {
  md: 'h-9 px-4',
  sm: 'h-8 px-3',
}

/**
 * The one button of the interface. `type` defaults to `button` because a button inside a
 * form that forgets it submits, and every accidental submit here is a write to the API.
 */
export function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`.trim()}
      type={type}
      {...rest}
    >
      {children}
    </button>
  )
}
