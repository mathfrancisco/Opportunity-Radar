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
    colorBorder: 'var(--color-control-line)',
    colorRing: 'var(--color-accent)',
    borderRadius: 'var(--radius-control)',
    fontFamily: 'var(--font-sans)',
  },
  elements: {
    // Clerk derives field borders from its own alpha mix, which vanishes on the dark surface.
    // The control line holds 3:1 against the field (DESIGN §6.2).
    formFieldInput: 'border! border-solid! border-control-line!',
    socialButtonsBlockButton: 'border! border-solid! border-control-line!',
    // At 320px the card must shrink with the 16px gutter of the shell, not push past it.
    rootBox: { width: '100%', minWidth: 0 },
    cardBox: { width: '100%', maxWidth: '100%', minWidth: 0 },
  },
}
