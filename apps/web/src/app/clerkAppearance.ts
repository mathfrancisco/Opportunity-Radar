import type { ClerkAppearanceTheme } from '@clerk/react/types'

/**
 * Clerk components follow the Bateia tokens. Every value is a `var(--…)` token from styles.css,
 * so Clerk switches with `data-theme` and `prefers-color-scheme` without picking colours per theme.
 */
export const clerkAppearance: ClerkAppearanceTheme = {
  variables: {
    colorPrimary: 'var(--color-accent)',
    colorPrimaryForeground: 'var(--color-surface)',
    colorBackground: 'var(--color-surface)',
    colorForeground: 'var(--color-ink)',
    colorMutedForeground: 'var(--color-muted)',
    colorMuted: 'var(--color-panel)',
    colorInput: 'var(--color-surface)',
    colorInputForeground: 'var(--color-ink)',
    colorDanger: 'var(--color-danger-ink)',
    colorBorder: 'var(--color-line)',
    colorRing: 'var(--color-accent)',
    borderRadius: 'var(--radius-control)',
    fontFamily: 'var(--font-sans)',
  },
}
