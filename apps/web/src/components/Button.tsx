import { type ButtonHTMLAttributes, type ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary'
export type ButtonSize = 'md' | 'sm'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
}

const base =
  'rounded-xl font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ' +
  'focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-accent'

const variants: Record<ButtonVariant, string> = {
  primary: 'bg-ink text-surface hover:bg-ink-hover',
  secondary: 'border border-line-strong font-medium hover:border-ink',
}

const sizes: Record<ButtonSize, string> = {
  md: 'px-5 py-3 text-sm',
  sm: 'px-4 py-2 text-sm',
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
