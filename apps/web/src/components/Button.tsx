import { type ButtonHTMLAttributes, type ReactNode } from 'react'
import { Link, type LinkProps } from 'react-router-dom'

export type ButtonVariant = 'primary' | 'secondary'
export type ButtonSize = 'md' | 'sm'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
}

interface ButtonLinkProps extends Omit<LinkProps, 'className'> {
  variant?: ButtonVariant
  size?: ButtonSize
  className?: string
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

function buttonClassName(variant: ButtonVariant, size: ButtonSize, className: string) {
  return `${base} ${variants[variant]} ${sizes[size]} ${className}`.trim()
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
      className={buttonClassName(variant, size, className)}
      type={type}
      {...rest}
    >
      {children}
    </button>
  )
}

/** A real navigation link with the same visual intent and target size as a Button. */
export function ButtonLink({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link className={buttonClassName(variant, size, className)} {...rest}>
      {children}
    </Link>
  )
}
